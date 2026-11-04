"""Alertes GPS (0061) : excès de vitesse, zone interdite, sortie de site ; prise en compte et réglages.

Les alertes naissent à l'ingestion de positions mesurées (traceur ou téléphone), seulement pour la mesure la
plus récente de l'engin ; leur lecture et leur prise en compte sont limitées au site et à la société.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401


def _tracker(client: TestClient, w: World, vehicle: str):  # type: ignore[no-untyped-def]  # noqa: F811
    device = "fictif-" + uuid.uuid4().hex
    token = client.post(
        f"{API}/vehicles/{vehicle}/gps/tracker", headers=w.ops.headers, json={"device_id": device}
    ).json()["token"]
    start = datetime.now(UTC)
    state = {"seq": 0}

    def send(seconds: int, lat: float, lon: float, speed: float | None) -> int:
        state["seq"] += 1
        body: dict[str, object] = {
            "device_id": device,
            "sequence": state["seq"],
            "latitude": lat,
            "longitude": lon,
            "recorded_at": (start + timedelta(seconds=seconds)).isoformat(),
        }
        if speed is not None:
            body["speed_kmh"] = speed
        return client.post(
            f"{API}/gps/telemetry", headers={"Authorization": f"Bearer {token}"}, json=body
        ).status_code

    return send


def _alerts(client: TestClient, headers: dict[str, str], **params: object) -> list[dict]:  # type: ignore[type-arg]
    resp = client.get(f"{API}/gps/alerts", headers=headers, params={"page_size": 100, **params})
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]  # type: ignore[no-any-return]


def test_overspeed_opens_tracks_peak_closes_and_ignores_late_points(
    client: TestClient,
    w: World,  # noqa: F811
) -> None:
    vehicle = _vehicle(client, w)
    site = str(w.t.sites["S1"])
    send = _tracker(client, w, vehicle)
    assert send(5, 10.0, -12.0, 90.0) == 204  # pas encore de limite : aucune alerte
    assert _alerts(client, w.ops.headers) == []

    policy = client.put(f"{API}/sites/{site}/gps-policy", headers=w.ops.headers, json={"speed_limit_kmh": 50})
    assert policy.status_code == 200 and policy.json()["speed_limit_kmh"] == "50.0"
    for seconds, speed in ((10, 40.0), (15, 62.0), (20, 70.0), (25, None), (30, 45.0), (40, 80.0)):
        assert send(seconds, 10.0, -12.0, speed) == 204
    # Position tardive (mesurée avant la dernière) : stockée, sans effet sur les alertes.
    assert send(35, 10.0, -12.0, 120.0) == 204

    alerts = _alerts(client, w.ops.headers, site_id=site)
    assert [a["kind"] for a in alerts] == ["OVERSPEED", "OVERSPEED"]
    latest, first = alerts
    assert (first["peak_speed_kmh"], first["speed_limit_kmh"]) == (70.0, "50.0")
    assert first["closed_at"] is not None and first["fleet_number"].startswith("P-")
    assert latest["closed_at"] is None and latest["peak_speed_kmh"] == 80.0

    # Limite retirée : la mesure suivante ferme l'alerte ouverte, rien de nouveau ne s'ouvre.
    assert (
        client.put(f"{API}/sites/{site}/gps-policy", headers=w.ops.headers, json={}).json()["speed_limit_kmh"]
        is None
    )
    assert send(45, 10.0, -12.0, 95.0) == 204
    assert all(a["closed_at"] is not None for a in _alerts(client, w.ops.headers))


def test_zone_alerts_on_restricted_entry_and_site_boundary_exit(
    client: TestClient,
    w: World,  # noqa: F811
) -> None:
    vehicle = _vehicle(client, w)
    site = str(w.t.sites["S1"])
    zones = {
        "LIMITE": ("SITE_BOUNDARY", [(-12.10, 9.90), (-11.90, 9.90), (-11.90, 10.10), (-12.10, 10.10)]),
        "INTERDIT": ("RESTRICTED", [(-12.02, 9.98), (-11.98, 9.98), (-11.98, 10.02), (-12.02, 10.02)]),
    }
    for code, (kind, ring) in zones.items():
        made = client.post(
            f"{API}/geofences",
            headers=w.ops.headers,
            json={"site_id": site, "code": code, "name": f"Zone {code}", "kind": kind, "coordinates": ring},
        )
        assert made.status_code == 201, made.text
    send = _tracker(client, w, vehicle)
    assert send(5, 10.05, -12.05, 20.0) == 204  # premier point : état initial, aucune alerte
    assert send(10, 10.00, -12.00, 15.0) == 204  # entrée en zone interdite
    assert send(15, 10.05, -12.05, 15.0) == 204  # sortie de la zone interdite : pas d'alerte
    assert send(20, 10.30, -12.30, 30.0) == 204  # sortie de la limite du site
    alerts = _alerts(client, w.ops.headers)
    assert [(a["kind"], a["geofence_name"]) for a in alerts] == [
        ("SITE_BOUNDARY_EXIT", "Zone LIMITE"),
        ("RESTRICTED_ZONE_ENTRY", "Zone INTERDIT"),
    ]
    assert all(a["closed_at"] == a["opened_at"] for a in alerts)
    assert alerts[1]["latitude"] == 10.0


def test_acknowledge_policy_and_isolation(client: TestClient, api: Api, w: World) -> None:  # noqa: F811
    vehicle = _vehicle(client, w)
    site = str(w.t.sites["S1"])
    client.put(f"{API}/sites/{site}/gps-policy", headers=w.ops.headers, json={"speed_limit_kmh": 30})
    send = _tracker(client, w, vehicle)
    assert send(5, 10.0, -12.0, 55.0) == 204
    (alert,) = _alerts(client, w.ops.headers)
    url = f"{API}/gps/alerts/{alert['gps_alert_id']}/acknowledge"

    dispatcher_s2 = api.user(w.t, "DISPATCHER", "SITE", "S2")
    auditor = api.user(w.t, "AUDITOR")
    outsider = api.user(api.tenant(), "OPS_MANAGER")
    assert client.post(url, headers=dispatcher_s2.headers, json={}).status_code == 404
    assert client.post(url, headers=outsider.headers, json={}).status_code == 404
    assert client.post(url, headers=auditor.headers, json={}).status_code == 403
    assert _alerts(client, dispatcher_s2.headers) == []
    assert _alerts(client, outsider.headers) == []
    assert len(_alerts(client, auditor.headers, unacknowledged=True)) == 1
    assert (
        client.get(f"{API}/gps/alerts", headers=outsider.headers, params={"site_id": site}).status_code == 404
    )

    done = client.post(url, headers=w.dispatcher.headers, json={"note": "conducteur prévenu"})
    assert done.status_code == 200, done.text
    assert done.json()["acknowledged_by"] == str(w.dispatcher.user_id)
    assert client.post(url, headers=w.dispatcher.headers, json={}).status_code == 409
    assert _alerts(client, auditor.headers, unacknowledged=True) == []
    events = client.get(f"{API}/audit-events", headers=w.t.admin.headers).json()["items"]
    assert any(e["action"] == "fleet.gps.alert.acknowledge" for e in events)
    assert any(e["action"] == "fleet.gps.policy.update" for e in events)

    # Réglage : réservé à l'exploitation ; bornes contrôlées.
    policy = f"{API}/sites/{site}/gps-policy"
    assert client.put(policy, headers=w.dispatcher.headers, json={"speed_limit_kmh": 40}).status_code == 403
    for bad in (0, 300, "abc"):
        assert client.put(policy, headers=w.ops.headers, json={"speed_limit_kmh": bad}).status_code == 422
    assert client.get(policy, headers=outsider.headers).status_code == 404


def test_phone_positions_raise_overspeed_alerts(client: TestClient, w: World) -> None:  # noqa: F811
    vehicle = _vehicle(client, w)
    client.put(
        f"{API}/sites/{w.t.sites['S1']}/gps-policy", headers=w.ops.headers, json={"speed_limit_kmh": 20}
    )
    share = client.post(
        f"{API}/me/gps/shares", headers=w.ops.headers, json={"vehicle_id": vehicle, "consent": True}
    ).json()["phone_share_id"]
    point = {"latitude": 9.5, "longitude": -13.7, "accuracy_m": 8.0, "speed_kmh": 33.0}
    sent = client.post(
        f"{API}/me/gps/shares/{share}/positions",
        headers=w.ops.headers,
        json={**point, "recorded_at": datetime.now(UTC).isoformat()},
    )
    assert sent.status_code == 204, sent.text
    (alert,) = _alerts(client, w.ops.headers)
    assert (alert["kind"], alert["peak_speed_kmh"], alert["vehicle_id"]) == ("OVERSPEED", 33.0, vehicle)
