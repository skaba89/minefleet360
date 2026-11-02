"""GPS avancé : géofences, trajets, zones, immobilisations, rétention (docs/LIVRAISON_GPS_AVANCE.md)."""

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from tests.conftest import API, Account, Api, TenantFixture

# Zone carrée d'environ 1,1 km de côté autour de la fosse fictive.
SQUARE = [(-13.710, 9.500), (-13.700, 9.500), (-13.700, 9.510), (-13.710, 9.510)]


@dataclass
class World:
    t: TenantFixture
    other: TenantFixture
    ops: Account
    ops_s2: Account
    hse: Account
    dispatcher: Account
    other_ops: Account
    vehicle: str


def _vehicle(client: TestClient, t: TenantFixture, site: str) -> str:
    category = client.get(f"{API}/vehicle-categories", headers=t.admin.headers).json()[0][
        "vehicle_category_id"
    ]
    resp = client.post(
        f"{API}/vehicles",
        headers=t.admin.headers,
        json={
            "site_id": str(t.sites[site]),
            "vehicle_category_id": category,
            "fleet_number": f"G-{uuid.uuid4().hex[:6]}",
        },
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["vehicle_id"])


@pytest.fixture(scope="module")
def w(api: Api, client: TestClient) -> World:
    t, other = api.tenant(), api.tenant()
    return World(
        t=t,
        other=other,
        ops=api.user(t, "OPS_MANAGER"),
        ops_s2=api.user(t, "OPS_MANAGER", "SITE", "S2"),
        hse=api.user(t, "HSE"),
        dispatcher=api.user(t, "DISPATCHER", "SITE", "S1"),
        other_ops=api.user(other, "OPS_MANAGER"),
        vehicle=_vehicle(client, t, "S1"),
    )


def _insert(t: TenantFixture, vehicle: str, rows: list[dict[str, object]]) -> None:
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(t.tenant_id)})
            conn.execute(
                text(
                    "INSERT INTO fleet_gps_position (tenant_id, vehicle_id, site_id, device_id, latitude, "
                    "longitude, speed_kmh, accuracy_m, recorded_at, received_at) VALUES (:tenant, :vehicle, "
                    ":site, :device, :lat, :lon, :speed, :acc, :at, :received)"
                ),
                [
                    {
                        "tenant": str(t.tenant_id),
                        "vehicle": vehicle,
                        "site": str(t.sites["S1"]),
                        "device": "traceur-fictif",
                        "speed": None,
                        "acc": 10.0,
                        "received": r["at"],
                        **r,
                    }
                    for r in rows
                ],
            )
    finally:
        engine.dispose()


def _geofence(client: TestClient, w: World, code: str, coordinates=None, headers=None):  # type: ignore[no-untyped-def]
    return client.post(
        f"{API}/geofences",
        headers=headers or w.hse.headers,
        json={
            "site_id": str(w.t.sites["S1"]),
            "code": code,
            "name": f"Zone {code}",
            "kind": "LOADING_AREA",
            "coordinates": coordinates or SQUARE,
        },
    )


def _track(
    client: TestClient, headers: dict[str, str], vehicle: str, start: datetime, end: datetime, **extra
):  # type: ignore[no-untyped-def]
    params = {"from": start.isoformat(), "to": end.isoformat(), "purpose": "INCIDENT_INVESTIGATION", **extra}
    return client.get(f"{API}/vehicles/{vehicle}/gps/track", headers=headers, params=params)


def test_geofence_validation(client: TestClient, w: World) -> None:
    created = _geofence(client, w, "FOSSE-NORD")
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["coordinates"][0] == body["coordinates"][-1] and 1_000_000 < body["area_m2"] < 1_500_000
    assert _geofence(client, w, "fosse-nord").json()["code"] == "DUPLICATE_GEOFENCE_CODE"
    bowtie = [(-13.71, 9.50), (-13.70, 9.51), (-13.70, 9.50), (-13.71, 9.51)]
    assert _geofence(client, w, "NOEUD", bowtie).json()["code"] == "GEOFENCE_INVALID"
    tiny = [(-13.7, 9.5), (-13.69999, 9.5), (-13.69999, 9.50001)]
    assert _geofence(client, w, "MINUSCULE", tiny).json()["code"] == "GEOFENCE_INVALID"
    assert _geofence(client, w, "HORS", [(-200, 9.5), (-13.7, 9.5), (-13.7, 9.6)]).status_code == 422
    assert _geofence(client, w, "DISP", headers=w.dispatcher.headers).status_code == 403
    listed = client.get(f"{API}/geofences", headers=w.dispatcher.headers).json()
    assert "FOSSE-NORD" in {g["code"] for g in listed}
    assert client.get(f"{API}/geofences", headers=w.other_ops.headers).json() == []
    foreign = client.post(
        f"{API}/geofences/{body['site_geofence_id']}/deactivate", headers=w.other_ops.headers
    )
    assert foreign.status_code == 404


def test_track_events_stops_gaps_and_audit(client: TestClient, w: World) -> None:
    vehicle = _vehicle(client, w.t, "S1")
    fence = _geofence(client, w, f"Z-{uuid.uuid4().hex[:5]}").json()
    t0 = datetime.now(UTC) - timedelta(hours=3)
    rows: list[dict[str, object]] = []
    # Approche hors zone, entrée, arrêt de 20 min dans la zone, sortie.
    for i, lat in enumerate([9.490, 9.495, 9.4995, 9.5020, 9.5050]):
        rows.append({"lat": lat, "lon": -13.705, "at": t0 + timedelta(minutes=2 * i)})
    for i in range(1, 11):
        rows.append({"lat": 9.5050, "lon": -13.705, "at": t0 + timedelta(minutes=8 + 2 * i)})
    rows.append({"lat": 9.5080, "lon": -13.705, "at": t0 + timedelta(minutes=30)})
    rows.append({"lat": 9.5150, "lon": -13.705, "at": t0 + timedelta(minutes=32)})
    # Point imprécis à l'intérieur pendant la sortie : ignoré (pas de fausse entrée).
    rows.append({"lat": 9.5050, "lon": -13.705, "at": t0 + timedelta(minutes=33), "acc": 500.0})
    # Saut aberrant de plusieurs dizaines de km en 2 minutes : ignoré.
    rows.append({"lat": 9.900, "lon": -13.705, "at": t0 + timedelta(minutes=34)})
    # Trou de réception de 40 minutes puis message reçu 12 minutes en retard.
    rows.append(
        {
            "lat": 9.5160,
            "lon": -13.705,
            "at": t0 + timedelta(minutes=74),
            "received": t0 + timedelta(minutes=86),
        }
    )
    _insert(w.t, vehicle, rows)

    resp = _track(client, w.hse.headers, vehicle, t0 - timedelta(minutes=5), t0 + timedelta(hours=2))
    assert resp.status_code == 200, resp.text
    track = resp.json()
    assert len(track["points"]) == len(rows) and track["truncated"] is False
    assert track["ignored_points"] == 2 and track["late_points"] == 1
    # D'autres zones actives du site peuvent recouvrir le même carré : on suit celle du test.
    events = [
        e["event_type"]
        for e in track["geofence_events"]
        if e["site_geofence_id"] == fence["site_geofence_id"]
    ]
    assert events == ["ENTER", "EXIT"]
    assert len(track["stops"]) == 1 and track["stops"][0]["minutes"] >= 18
    assert [g["minutes"] for g in track["gaps"]] == [42]
    assert 2.5 < track["distance_km"] < 3.0  # environ 2,8 km : le saut et le trou ne sont pas comptés
    assert track["signal"] == "LOST"

    feed = client.get(
        f"{API}/gps/geofence-events",
        headers=w.ops.headers,
        params={
            "site_id": str(w.t.sites["S1"]),
            "purpose": "OPERATIONS_REVIEW",
            "from": (t0 - timedelta(minutes=5)).isoformat(),
            "to": (t0 + timedelta(hours=2)).isoformat(),
        },
    )
    assert feed.status_code == 200, feed.text
    mine = [
        e["event_type"]
        for e in feed.json()
        if e["vehicle_id"] == vehicle and e["site_geofence_id"] == fence["site_geofence_id"]
    ]
    assert mine == ["ENTER", "EXIT"]

    audit = client.get(
        f"{API}/audit-events", headers=w.t.admin.headers, params={"action": "fleet.gps.track.read"}
    ).json()["items"]
    assert any(e["entity_id"] == vehicle and e["reason"] == "INCIDENT_INVESTIGATION" for e in audit)

    deactivated = client.post(
        f"{API}/geofences/{fence['site_geofence_id']}/deactivate", headers=w.hse.headers
    )
    assert deactivated.status_code == 200 and deactivated.json()["active"] is False
    again = _track(client, w.hse.headers, vehicle, t0 - timedelta(minutes=5), t0 + timedelta(hours=2)).json()
    assert fence["site_geofence_id"] not in {e["site_geofence_id"] for e in again["geofence_events"]}


def test_history_access_rules(client: TestClient, w: World) -> None:
    now = datetime.now(UTC)
    start = now - timedelta(hours=1)
    assert _track(client, w.dispatcher.headers, w.vehicle, start, now).status_code == 403
    no_purpose = client.get(
        f"{API}/vehicles/{w.vehicle}/gps/track",
        headers=w.ops.headers,
        params={"from": start.isoformat(), "to": now.isoformat()},
    )
    assert no_purpose.status_code == 422
    assert _track(client, w.ops.headers, w.vehicle, start, now, purpose="CURIOSITY").status_code == 422
    assert _track(client, w.ops.headers, w.vehicle, now - timedelta(hours=30), now).status_code == 422
    assert _track(client, w.ops.headers, w.vehicle, now, start).status_code == 422
    assert _track(client, w.ops_s2.headers, w.vehicle, start, now).status_code == 404
    assert _track(client, w.other_ops.headers, w.vehicle, start, now).status_code == 404
    empty = _track(client, w.ops.headers, w.vehicle, start, now).json()
    assert empty["points"] == [] and empty["signal"] == "NONE" and empty["distance_km"] == 0
    feed = client.get(
        f"{API}/gps/geofence-events",
        headers=w.ops_s2.headers,
        params={"site_id": str(w.t.sites["S1"]), "purpose": "SECURITY"},
    )
    assert feed.status_code == 404


def test_track_load_is_bounded(client: TestClient, w: World) -> None:
    vehicle = _vehicle(client, w.t, "S1")
    _geofence(client, w, f"L-{uuid.uuid4().hex[:5]}")
    t0 = datetime.now(UTC) - timedelta(hours=10)
    rows: list[dict[str, object]] = [
        {"lat": 9.49 + (i % 200) * 0.0001, "lon": -13.705, "at": t0 + timedelta(seconds=5 * i)}
        for i in range(5001)
    ]
    _insert(w.t, vehicle, rows)
    started = time.perf_counter()
    resp = _track(client, w.ops.headers, vehicle, t0, t0 + timedelta(hours=8))
    elapsed = time.perf_counter() - started
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["points"]) == 5000 and resp.json()["truncated"] is True
    assert elapsed < 10, elapsed  # budget large pour un poste de développement ; à mesurer en recette


def test_retention_purge_is_owner_only(client: TestClient, w: World) -> None:
    vehicle = _vehicle(client, w.t, "S1")
    old = datetime.now(UTC) - timedelta(days=40)
    _insert(w.t, vehicle, [{"lat": 9.5, "lon": -13.7, "at": old + timedelta(minutes=i)} for i in range(3)])
    _insert(w.t, vehicle, [{"lat": 9.5, "lon": -13.7, "at": datetime.now(UTC) - timedelta(days=1)}])
    app_engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    owner = create_engine(get_settings().database_url(owner=True), pool_size=1, max_overflow=0)
    cutoff = datetime.now(UTC) - timedelta(days=30)
    try:
        with app_engine.connect() as conn:
            with pytest.raises(DBAPIError):
                conn.execute(text("SELECT app.purge_gps_positions(:c, false)"), {"c": cutoff})
            conn.rollback()
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            conn.execute(text("SELECT set_config('app.gps_retention_purge', 'on', true)"))
            with pytest.raises(DBAPIError):
                conn.execute(text("DELETE FROM fleet_gps_position WHERE vehicle_id = :v"), {"v": vehicle})
            conn.rollback()
        with owner.begin() as conn:
            with pytest.raises(DBAPIError):
                with conn.begin_nested():
                    conn.execute(
                        text("SELECT app.purge_gps_positions(:c, false)"),
                        {"c": datetime.now(UTC) - timedelta(days=2)},
                    )
            assert (
                conn.execute(text("SELECT app.purge_gps_positions(:c, true)"), {"c": cutoff}).scalar_one()
                >= 3
            )
            assert (
                conn.execute(text("SELECT app.purge_gps_positions(:c, false)"), {"c": cutoff}).scalar_one()
                >= 3
            )
        with app_engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            left = conn.execute(
                text("SELECT count(*) FROM fleet_gps_position WHERE vehicle_id = :v"), {"v": vehicle}
            ).scalar_one()
            assert left == 1
            with pytest.raises(DBAPIError):
                conn.execute(
                    text("UPDATE fleet_gps_position SET latitude = 0 WHERE vehicle_id = :v"), {"v": vehicle}
                )
    finally:
        app_engine.dispose()
        owner.dispose()
