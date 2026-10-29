"""Parcours HTTP réels : consentement, compte, périmètre, révocation et provenance."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_assignment import World, _action, _create, _driver, _vehicle, w  # noqa: F401


def _point() -> dict[str, object]:
    return {
        "latitude": 9.5,
        "longitude": -13.7,
        "accuracy_m": 12.0,
        "recorded_at": datetime.now(UTC).isoformat(),
    }


def test_phone_consent_owner_stop_and_latest(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    vehicle = _vehicle(client, w)
    body = {"vehicle_id": vehicle, "consent": True}
    for consent in (False, "true", 1):
        denied = client.post(f"{API}/me/gps/shares", headers=w.ops.headers, json={**body, "consent": consent})
        assert denied.status_code == 422, denied.text
    created = client.post(f"{API}/me/gps/shares", headers=w.ops.headers, json=body)
    assert created.status_code == 201, created.text
    share = created.json()["phone_share_id"]
    path = f"{API}/me/gps/shares/{share}"
    other = api.user(w.t, "OPS_MANAGER")
    assert client.post(path + "/positions", headers=other.headers, json=_point()).status_code == 404
    assert client.post(path + "/stop", headers=other.headers).status_code == 404
    invalid = client.post(
        path + "/positions", headers=w.ops.headers, json={**_point(), "tenant_id": str(w.t.tenant_id)}
    )
    assert invalid.status_code == 422
    stale = client.post(
        path + "/positions",
        headers=w.ops.headers,
        json={**_point(), "recorded_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat()},
    )
    assert stale.status_code == 422
    point = client.post(path + "/positions", headers=w.ops.headers, json=_point())
    assert point.status_code == 204, point.text
    latest = client.get(f"{API}/vehicles/gps/latest", headers=w.ops.headers).json()
    row = next(p for p in latest if p["vehicle_id"] == vehicle)
    assert row["source"] == "PHONE" and row["source_active"] is True
    assert "user_account_id" not in row and "device_id" not in row
    fast = client.post(path + "/positions", headers=w.ops.headers, json=_point())
    assert fast.status_code == 429, fast.text
    assert client.post(path + "/stop", headers=w.ops.headers).status_code == 204
    assert client.post(path + "/stop", headers=w.ops.headers).status_code == 204
    assert client.post(path + "/positions", headers=w.ops.headers, json=_point()).status_code == 409
    latest = client.get(f"{API}/vehicles/gps/latest", headers=w.ops.headers).json()
    assert next(p for p in latest if p["vehicle_id"] == vehicle)["source_active"] is False
    events = client.get(f"{API}/audit-events", headers=w.t.admin.headers).json()["items"]
    assert any(e["action"] == "gps.phone.start" for e in events)
    assert "latitude" not in str(events) and "longitude" not in str(events)


def test_phone_scope_cross_tenant_and_replacement(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    vehicle = _vehicle(client, w)
    other_site = _vehicle(client, w, "S2")

    def start(target: str, headers: dict[str, str]):  # type: ignore[no-untyped-def]
        return client.post(
            f"{API}/me/gps/shares", headers=headers, json={"vehicle_id": target, "consent": True}
        )

    assert start(other_site, w.dispatcher.headers).status_code == 404
    outsider = api.user(api.tenant(), "OPS_MANAGER")
    assert start(vehicle, outsider.headers).status_code == 404
    first = start(vehicle, w.ops.headers).json()["phone_share_id"]
    second = start(other_site, w.ops.headers)
    assert second.status_code == 201, second.text
    assert (
        client.post(
            f"{API}/me/gps/shares/{first}/positions", headers=w.ops.headers, json=_point()
        ).status_code
        == 409
    )
    options = client.get(f"{API}/me/gps/vehicles", headers=w.dispatcher.headers)
    assert options.status_code == 200
    assert other_site not in {p["vehicle_id"] for p in options.json()}


def test_driver_only_own_active_assignment(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    vehicle, driver = _vehicle(client, w), _driver(client, w)
    other_vehicle = _vehicle(client, w)
    account = api.user(w.t, "DRIVER", "SITE", "S1")
    url = f"{API}/drivers/{driver}/gps-account"
    assert client.get(f"{API}/me/gps/vehicles", headers=account.headers).json() == []
    bad_link = client.post(url, headers=w.t.admin.headers, json={"user_account_id": str(w.hr.user_id)})
    assert bad_link.status_code == 422
    linked = client.post(url, headers=w.t.admin.headers, json={"user_account_id": str(account.user_id)})
    assert linked.status_code == 200, linked.text
    assignment = _create(client, w, vehicle, driver)
    assert assignment.status_code == 201, assignment.text
    options = client.get(f"{API}/me/gps/vehicles", headers=account.headers)
    assert {v["vehicle_id"] for v in options.json()} == {vehicle}
    body = {"vehicle_id": other_vehicle, "consent": True}
    assert client.post(f"{API}/me/gps/shares", headers=account.headers, json=body).status_code == 404
    body["vehicle_id"] = vehicle
    started = client.post(f"{API}/me/gps/shares", headers=account.headers, json=body)
    assert started.status_code == 201, started.text
    share = started.json()["phone_share_id"]
    assert (
        client.post(
            f"{API}/me/gps/shares/{share}/positions", headers=account.headers, json=_point()
        ).status_code
        == 204
    )
    done = _action(client, w, assignment.json()["vehicle_assignment_id"], "complete", {})
    assert done.status_code == 200, done.text
    denied = client.post(f"{API}/me/gps/shares/{share}/positions", headers=account.headers, json=_point())
    assert denied.status_code == 404, denied.text
    assert client.post(f"{API}/me/gps/shares/{share}/stop", headers=account.headers).status_code == 204


def test_tracker_provision_ingest_replay_secret_and_revoke(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    vehicle = _vehicle(client, w)
    device = "fictif-" + uuid.uuid4().hex
    path = f"{API}/vehicles/{vehicle}/gps/tracker"
    created = client.post(path, headers=w.ops.headers, json={"device_id": device})
    assert created.status_code == 201, created.text
    token = created.json()["token"]
    assert token.startswith("gps_")
    assert "token" not in client.get(path, headers=w.ops.headers).json()
    assert client.post(path, headers=w.ops.headers, json={"device_id": device}).status_code == 409
    headers = {"Authorization": f"Bearer {token}"}
    body = {**_point(), "device_id": device, "sequence": 1}
    assert client.post(f"{API}/gps/telemetry", json=body).status_code == 401
    # Un jeton utilisateur ne vaut jamais jeton d'équipement.
    assert client.post(f"{API}/gps/telemetry", headers=w.ops.headers, json=body).status_code == 401
    wrong = token[:-1] + ("a" if token[-1] != "a" else "b")
    assert (
        client.post(
            f"{API}/gps/telemetry", headers={"Authorization": f"Bearer {wrong}"}, json=body
        ).status_code
        == 401
    )
    accepted = client.post(f"{API}/gps/telemetry", headers=headers, json=body)
    assert accepted.status_code == 204, accepted.text
    replay = client.post(f"{API}/gps/telemetry", headers=headers, json=body)
    assert replay.status_code == 409, replay.text
    latest = client.get(f"{API}/vehicles/gps/latest", headers=w.ops.headers).json()
    assert next(p for p in latest if p["vehicle_id"] == vehicle)["source"] == "TRACKER"
    outside = api.user(api.tenant(), "OPS_MANAGER")
    assert client.get(path, headers=outside.headers).status_code == 404
    assert client.get(f"{API}/vehicles/gps/latest", headers=outside.headers).json() == []
    assert client.post(path + "/revoke", headers=w.ops.headers).status_code == 204
    assert (
        client.post(f"{API}/gps/telemetry", headers=headers, json={**body, "sequence": 2}).status_code == 401
    )
    latest = client.get(f"{API}/vehicles/gps/latest", headers=w.ops.headers).json()
    assert next(p for p in latest if p["vehicle_id"] == vehicle)["source_active"] is False
