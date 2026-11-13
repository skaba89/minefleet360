"""Métriques de qualité GPS (SLO) : percentiles d'ingestion, fraîcheur, portée et refus.

Complète le banc synthétique par la mesure côté plateforme : les latences sont produites par la
voie d'ingestion réelle (jeton traceur, horodatages contrôlés), les agrégats sont vérifiés par
bornes (l'horloge serveur avance pendant l'essai, jamais contre une égalité stricte).
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401

TOLERANCE_S = 30.0


def _tracker(client: TestClient, w: World, vehicle: str) -> tuple[str, str]:  # noqa: F811
    device = "fictif-" + uuid.uuid4().hex
    created = client.post(
        f"{API}/vehicles/{vehicle}/gps/tracker", headers=w.ops.headers, json={"device_id": device}
    )
    assert created.status_code == 201, created.text
    return device, created.json()["token"]


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


def test_metrics_percentiles_skew_and_staleness(client: TestClient, w: World) -> None:  # noqa: F811
    now = datetime.now(UTC)
    vehicle_a = _vehicle(client, w, site="S1")
    vehicle_b = _vehicle(client, w, site="S2")
    device_a, token_a = _tracker(client, w, vehicle_a)
    device_b, token_b = _tracker(client, w, vehicle_b)

    # Engin A : latences 10/20/30 s puis une horloge de boîtier en avance (+5 s).
    for sequence, delay in ((1, 10), (2, 20), (3, 30)):
        _send(client, device_a, token_a, sequence, now - timedelta(seconds=delay))
    _send(client, device_a, token_a, 4, now + timedelta(seconds=5))
    # Engin B : une seule position vieille de 40 min (au-delà du seuil d'obsolescence de 30 min).
    _send(client, device_b, token_b, 1, now - timedelta(minutes=40))

    served = client.get(f"{API}/gps/metrics", headers=w.ops.headers, params={"minutes": 60})
    assert served.status_code == 200, served.text
    body = served.json()
    assert body["window_minutes"] == 60 and body["positions_count"] == 4

    latency = body["ingestion_latency"]
    assert latency["negative_skew_count"] == 1
    assert 10 - TOLERANCE_S <= latency["p50_s"] <= 20 + TOLERANCE_S
    assert latency["p50_s"] <= latency["p95_s"] <= latency["p99_s"] <= latency["max_s"] + 0.01
    assert latency["p95_s"] >= 30 - TOLERANCE_S

    freshness = body["freshness"]
    assert freshness["vehicles_reporting"] == 2
    # L'engin A est frais (position datée du futur → âge plancher 0) ; l'engin B est obsolète.
    assert freshness["stale_count"] == 1
    assert 40 * 60 - TOLERANCE_S <= freshness["max_age_s"] <= 40 * 60 + TOLERANCE_S
    assert freshness["p50_age_s"] <= freshness["p95_age_s"] <= freshness["max_age_s"] + 0.01


def test_metrics_respect_scope_and_role(client: TestClient, api: Api, w: World) -> None:  # noqa: F811
    now = datetime.now(UTC)
    vehicle_s1 = _vehicle(client, w, site="S1")
    device, token = _tracker(client, w, vehicle_s1)
    _send(client, device, token, 1, now - timedelta(seconds=10))

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
