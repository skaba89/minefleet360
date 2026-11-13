"""Métriques de qualité GPS (SLO) : percentiles d'ingestion, fraîcheur, portée et refus.

La voie d'ingestion réelle produit la latence : le contrat GPS refuse toute position horodatée
avant l'activation du traceur (anti-attribution) et au-delà de 2 min dans le futur — la latence
positive s'obtient donc par un envoi différé après activation. L'obsolescence d'un engin au repos
ne peut pas passer par l'ingestion (aucune position antérieure à l'activation n'est acceptée) :
une position historique est semée en SQL, comme la référence de lecture de `test_gps_latest_read`.
"""

import time
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import new_session
from app.core.tenancy import set_tenant_context
from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401

TOLERANCE_S = 30.0


def _tracker(client: TestClient, w: World, vehicle: str) -> tuple[str, str, datetime]:  # noqa: F811
    device = "fictif-" + uuid.uuid4().hex
    created = client.post(
        f"{API}/vehicles/{vehicle}/gps/tracker", headers=w.ops.headers, json={"device_id": device}
    )
    assert created.status_code == 201, created.text
    return device, created.json()["token"], datetime.now(UTC)


def _send(client: TestClient, device: str, token: str, sequence: int, recorded_at: datetime) -> None:
    resp = client.post(
        f"{API}/gps/telemetry",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "device_id": device,
            "latitude": 9.5,
            "longitude": -13.7,
            "accuracy_m": 8.0,
            "recorded_at": recorded_at.isoformat(),
            "sequence": sequence,
        },
    )
    assert resp.status_code == 204, resp.text


def _seed_stale_position(w: World, vehicle: str, site: str, age_minutes: float) -> None:  # noqa: F811
    """Position historique semée hors ingestion : seule façon d'exister « avant l'activation »."""
    db = new_session()
    try:
        set_tenant_context(db, w.t.tenant_id)
        db.execute(
            text(
                "INSERT INTO fleet_gps_position (tenant_id, vehicle_id, site_id, device_id, "
                "latitude, longitude, recorded_at, received_at) "
                "VALUES (:t, :v, :s, :d, 9.5, -13.7, :r, :r)"
            ),
            {
                "t": w.t.tenant_id,
                "v": uuid.UUID(vehicle),
                "s": w.t.sites[site],
                "d": "fictif-semence-" + uuid.uuid4().hex[:8],
                "r": datetime.now(UTC) - timedelta(minutes=age_minutes),
            },
        )
        db.commit()
    finally:
        db.close()


def test_metrics_percentiles_skew_and_staleness(client: TestClient, w: World) -> None:  # noqa: F811
    vehicle_a = _vehicle(client, w, site="S1")
    vehicle_b = _vehicle(client, w, site="S2")
    device_a, token_a, activated = _tracker(client, w, vehicle_a)

    # Latences positives : estampillage juste après l'activation, transmission différée.
    time.sleep(6)
    _send(client, device_a, token_a, 1, activated + timedelta(seconds=1))
    _send(client, device_a, token_a, 2, activated + timedelta(seconds=4))
    _send(client, device_a, token_a, 3, activated + timedelta(seconds=5))
    # Horloge de boîtier en avance : estampillage dans le futur toléré (< 2 min du contrat).
    _send(client, device_a, token_a, 4, activated + timedelta(seconds=90))

    # Engin au repos : dernière position il y a 40 min (au-delà du seuil d'obsolescence de 30 min).
    _seed_stale_position(w, vehicle_b, "S2", age_minutes=40)

    served = client.get(f"{API}/gps/metrics", headers=w.ops.headers, params={"minutes": 60})
    assert served.status_code == 200, served.text
    body = served.json()
    assert body["window_minutes"] == 60 and body["positions_count"] == 4

    latency = body["ingestion_latency"]
    assert latency["negative_skew_count"] == 1
    assert 0 <= latency["p50_s"] <= 10
    assert latency["p50_s"] <= latency["p95_s"] <= latency["p99_s"] <= latency["max_s"] + 0.01
    assert 3 <= latency["p95_s"] <= 15  # la plus lente des transmissions différées ≈ 5 s

    freshness = body["freshness"]
    assert freshness["vehicles_reporting"] == 2
    # L'engin A est frais (estampillage futur → âge plancher 0) ; l'engin B est obsolète.
    assert freshness["stale_count"] == 1
    assert 40 * 60 - TOLERANCE_S <= freshness["max_age_s"] <= 40 * 60 + TOLERANCE_S
    assert freshness["p50_age_s"] <= freshness["p95_age_s"] <= freshness["max_age_s"] + 0.01


def test_metrics_respect_scope_and_role(client: TestClient, api: Api, w: World) -> None:  # noqa: F811
    vehicle_s1 = _vehicle(client, w, site="S1")
    device, token, activated = _tracker(client, w, vehicle_s1)
    time.sleep(1.2)
    _send(client, device, token, 1, activated + timedelta(seconds=1))

    ops_s1 = api.user(w.t, "OPS_MANAGER", "SITE", "S1")
    ops_s2 = api.user(w.t, "OPS_MANAGER", "SITE", "S2")
    auditor = api.user(w.t, "AUDITOR")

    mine = client.get(f"{API}/gps/metrics", headers=ops_s1.headers)
    assert mine.status_code == 200, mine.text
    assert mine.json()["positions_count"] == 1

    other = client.get(f"{API}/gps/metrics", headers=ops_s2.headers)
    assert other.status_code == 200, other.text
    body = other.json()
    assert body["positions_count"] == 0
    assert body["ingestion_latency"]["p50_s"] is None and body["freshness"]["vehicles_reporting"] == 0

    read_only = client.get(f"{API}/gps/metrics", headers=auditor.headers)
    assert read_only.status_code == 200 and read_only.json()["positions_count"] == 1

    denied = client.get(f"{API}/gps/metrics", headers=w.dispatcher.headers)
    assert denied.status_code == 403 and denied.json()["code"] == "PERMISSION_DENIED"

    # Une société étrangère ne voit rien (RLS + portée) — même empreinte qu'un tenant vide.
    outsider = api.tenant()
    foreign = client.get(f"{API}/gps/metrics", headers=outsider.admin.headers)
    assert foreign.status_code == 200 and foreign.json()["positions_count"] == 0


def test_metrics_window_is_bounded(client: TestClient, w: World) -> None:  # noqa: F811
    for minutes in ("0", "1441", "-5"):
        rejected = client.get(f"{API}/gps/metrics", headers=w.ops.headers, params={"minutes": minutes})
        assert rejected.status_code == 422, (minutes, rejected.text)
    ok = client.get(f"{API}/gps/metrics", headers=w.ops.headers, params={"minutes": 1440})
    assert ok.status_code == 200 and ok.json()["window_minutes"] == 1440
