"""Transactional replay of an offline work-order NOTE."""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401
from tests.test_maintenance import _act, _report


def test_note_idempotency_replays_without_new_event(
    client: TestClient,
    w: World,  # noqa: F811
    api: Api,
) -> None:
    chief = api.user(w.t, "WORKSHOP_CHIEF")
    vehicle = _vehicle(client, w)
    oid = _report(client, w, vehicle).json()["work_order_id"]
    assert _act(client, "decision", oid, chief.headers, action="APPROVE").status_code == 200
    assigned = _act(client, "decision", oid, chief.headers, action="ASSIGN", assigned_to=str(chief.user_id))
    assert assigned.status_code == 200
    url = f"/api/v1/work-orders/{oid}"
    version = client.get(url, headers=chief.headers).headers["ETag"]
    key = str(uuid.uuid4())
    headers = {**chief.headers, "If-Match": version, "Idempotency-Key": key}
    payload = {"action": "NOTE", "work_done": "Inspection hors ligne"}
    first = client.post(f"{url}/progress", headers=headers, json=payload)
    assert first.status_code == 200, first.text
    replay = client.post(f"{url}/progress", headers=headers, json=payload)
    assert replay.status_code == 200, replay.text
    assert replay.json()["work_done"] == "Inspection hors ligne"
    assert replay.json()["events"] == first.json()["events"]
    mismatched = client.post(
        f"{url}/progress", headers=headers, json={"action": "NOTE", "work_done": "Autre"}
    )
    assert mismatched.status_code == 409
