"""Relevés de compteur rejouables depuis l'outbox terrain (Idempotency-Key, phase 4 hors ligne)."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import API
from tests.test_assignment import World, _vehicle, w  # noqa: F401  (fixture w)


def _offline(client: TestClient, headers: dict[str, str], vehicle: str, key: str, body: dict[str, object]):  # type: ignore[no-untyped-def]
    return client.post(
        f"{API}/vehicles/{vehicle}/meter-readings", headers={**headers, "Idempotency-Key": key}, json=body
    )


def test_offline_meter_reading_replay_creates_it_once(client: TestClient, w: World) -> None:  # noqa: F811
    vehicle = _vehicle(client, w)
    base = datetime.now(UTC) - timedelta(hours=3)
    first_reading = {"meter_kind": "ODOMETER_KM", "value": 1000, "read_at": base.isoformat()}
    assert _offline(client, w.ops.headers, vehicle, str(uuid.uuid4()), first_reading).status_code == 201
    key = str(uuid.uuid4())
    body = {"meter_kind": "ODOMETER_KM", "value": 1050.5, "read_at": (base + timedelta(hours=2)).isoformat()}
    first = _offline(client, w.dispatcher.headers, vehicle, key, body)
    assert first.status_code == 201, first.text
    assert "Idempotency-Replayed" not in first.headers
    again = _offline(client, w.dispatcher.headers, vehicle, key, body)
    assert again.status_code == 201 and again.headers["Idempotency-Replayed"] == "true"
    reading_id = first.json()["vehicle_meter_reading_id"]
    assert again.json()["vehicle_meter_reading_id"] == reading_id
    listed = client.get(f"{API}/vehicles/{vehicle}/meter-readings", headers=w.ops.headers).json()["items"]
    assert sum(1 for r in listed if r["vehicle_meter_reading_id"] == reading_id) == 1
    assert len(listed) == 2
    audit = client.get(
        f"{API}/audit-events",
        headers=w.t.admin.headers,
        params={"action": "vehicle_meter.record", "entity_id": vehicle},
    ).json()["items"]
    assert len(audit) == 2  # relevé initial + relevé hors ligne, le rejeu n'ajoute rien
    # Même clé, autre contenu ou autre engin : refusé, jamais un second relevé.
    altered = _offline(client, w.dispatcher.headers, vehicle, key, {**body, "value": 1060})
    assert (altered.status_code, altered.json()["code"]) == (422, "IDEMPOTENCY_KEY_REUSED")
    other_vehicle = _vehicle(client, w)
    moved = _offline(client, w.dispatcher.headers, other_vehicle, key, body)
    assert (moved.status_code, moved.json()["code"]) == (422, "IDEMPOTENCY_KEY_REUSED")


def test_rejected_reading_does_not_consume_the_key_and_key_is_per_account(
    client: TestClient,
    w: World,  # noqa: F811
) -> None:
    vehicle = _vehicle(client, w)
    base = datetime.now(UTC) - timedelta(hours=2)
    start = {"meter_kind": "ODOMETER_KM", "value": 1000, "read_at": base.isoformat()}
    assert _offline(client, w.ops.headers, vehicle, str(uuid.uuid4()), start).status_code == 201
    key = str(uuid.uuid4())
    later = (base + timedelta(hours=1)).isoformat()
    implausible = _offline(client, w.ops.headers, vehicle, key, {**start, "value": 5000, "read_at": later})
    assert (
        implausible.status_code == 422 and implausible.json()["details"][0]["type"] == "implausible_increase"
    )
    # Le rejet a annulé la réservation de la clé : la saisie corrigée passe avec la même clé.
    corrected = {**start, "value": 1040, "read_at": later}
    ok = _offline(client, w.ops.headers, vehicle, key, corrected)
    assert ok.status_code == 201 and "Idempotency-Replayed" not in ok.headers
    # La clé est liée au compte : un autre compte ne rejoue pas le relevé d'autrui.
    theirs = _offline(client, w.dispatcher.headers, vehicle, key, corrected)
    assert theirs.status_code == 201 and "Idempotency-Replayed" not in theirs.headers
    assert theirs.json()["vehicle_meter_reading_id"] != ok.json()["vehicle_meter_reading_id"]
    # Sans le droit de relever : refusé avant toute réservation.
    assert _offline(client, w.hr.headers, vehicle, str(uuid.uuid4()), corrected).status_code == 403
