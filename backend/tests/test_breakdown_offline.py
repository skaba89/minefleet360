"""Signalement de panne rejouable depuis l'outbox terrain (Idempotency-Key, heure du constat ; phase 4)."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import API
from tests.test_assignment import World, _vehicle, w  # noqa: F401  (fixture w)
from tests.test_maintenance import _vehicle_status


def _offline(client: TestClient, headers: dict[str, str], key: str, body: dict[str, object]):  # type: ignore[no-untyped-def]
    return client.post(f"{API}/work-orders", headers={**headers, "Idempotency-Key": key}, json=body)


def test_offline_breakdown_replay_creates_one_work_order_at_the_observed_time(
    client: TestClient,
    w: World,  # noqa: F811
) -> None:
    vehicle = _vehicle(client, w)
    observed = datetime.now(UTC) - timedelta(hours=5)
    key = str(uuid.uuid4())
    body = {
        "vehicle_id": vehicle,
        "symptom_code": "BRAKES",
        "priority": "HIGH",
        "immobilize": True,
        "description": f"Freinage faible {key[:8]}",
        "reported_at": observed.isoformat(),
    }
    first = _offline(client, w.dispatcher.headers, key, body)
    assert first.status_code == 201, first.text
    order = first.json()
    assert "Idempotency-Replayed" not in first.headers
    assert datetime.fromisoformat(order["reported_at"]) == observed  # heure du constat, pas de l'envoi
    assert _vehicle_status(client, w, vehicle) == "IMMOBILIZED"
    again = _offline(client, w.dispatcher.headers, key, body)
    assert again.status_code == 201 and again.headers["Idempotency-Replayed"] == "true"
    assert (again.json()["work_order_id"], again.json()["reference"]) == (
        order["work_order_id"],
        order["reference"],
    )
    listed = client.get(
        f"{API}/work-orders", headers=w.ops.headers, params={"vehicle_id": vehicle, "page_size": 50}
    ).json()["items"]
    assert [o["work_order_id"] for o in listed] == [order["work_order_id"]]
    audit = client.get(
        f"{API}/audit-events",
        headers=w.t.admin.headers,
        params={"action": "work_order.request", "entity_id": order["work_order_id"]},
    ).json()
    assert audit["total"] == 1
    altered = _offline(client, w.dispatcher.headers, key, {**body, "priority": "NORMAL"})
    assert (altered.status_code, altered.json()["code"]) == (422, "IDEMPOTENCY_KEY_REUSED")


def test_observed_time_tolerance_rejection_and_permissions(client: TestClient, w: World) -> None:  # noqa: F811
    vehicle = _vehicle(client, w)
    base: dict[str, object] = {"vehicle_id": vehicle, "symptom_code": "ENGINE"}
    now = datetime.now(UTC)
    for at in (now - timedelta(days=8), now + timedelta(hours=1)):
        late = _offline(
            client, w.dispatcher.headers, str(uuid.uuid4()), {**base, "reported_at": at.isoformat()}
        )
        assert late.status_code == 422 and late.json()["details"][0]["type"] == "out_of_tolerance"
    # Un refus ne consomme pas la clé : la saisie corrigée passe avec la même clé.
    key = str(uuid.uuid4())
    bad = _offline(
        client, w.dispatcher.headers, key, {**base, "reported_at": (now - timedelta(days=9)).isoformat()}
    )
    assert bad.status_code == 422
    fixed = _offline(
        client, w.dispatcher.headers, key, {**base, "reported_at": (now - timedelta(days=1)).isoformat()}
    )
    assert fixed.status_code == 201 and "Idempotency-Replayed" not in fixed.headers
    # Sans heure de constat : comportement inchangé (heure de réception).
    plain = client.post(f"{API}/work-orders", headers=w.dispatcher.headers, json=base)
    assert plain.status_code == 201
    assert abs(datetime.fromisoformat(plain.json()["reported_at"]) - datetime.now(UTC)) < timedelta(minutes=1)
    # La clé est liée au compte ; un rôle sans droit de signaler est refusé avant toute réservation.
    theirs = _offline(
        client, w.ops.headers, key, {**base, "reported_at": (now - timedelta(days=1)).isoformat()}
    )
    assert theirs.status_code == 201 and theirs.json()["work_order_id"] != fixed.json()["work_order_id"]
    assert _offline(client, w.hr.headers, str(uuid.uuid4()), base).status_code == 403
    # Engin d'un autre site que celui du répartiteur : indiscernable d'un engin inexistant.
    other_site = _vehicle(client, w, "S2")
    foreign = _offline(client, w.dispatcher.headers, str(uuid.uuid4()), {**base, "vehicle_id": other_site})
    assert (foreign.status_code, foreign.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
