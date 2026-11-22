"""Recette HTTP du GPS différé, désactivé hors activation explicite."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from tests.conftest import API
from tests.test_assignment import World, _vehicle, w  # noqa: F401


def test_deferred_api(client: TestClient, w: World, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    vehicle = _vehicle(client, w)
    response = client.post(
        f"{API}/me/gps/shares",
        headers=w.ops.headers,
        json={"vehicle_id": vehicle, "consent": True},
    )
    assert response.status_code == 201, response.text
    share = response.json()
    url = f"{API}/me/gps/shares/{share['phone_share_id']}/deferred-positions"
    point_id = str(uuid.uuid4())
    payload = {
        "points": [
            {
                "client_point_id": point_id,
                "latitude": 9.5,
                "longitude": -13.7,
                "accuracy_m": 10,
                "recorded_at": share["started_at"],
            }
        ]
    }
    monkeypatch.setattr(get_settings(), "gps_deferred_enabled", False)
    assert client.post(url, headers=w.ops.headers, json=payload).status_code == 404
    monkeypatch.setattr(get_settings(), "gps_deferred_enabled", True)
    assert client.post(url, json=payload).status_code == 401
    assert client.post(url, headers=w.hr.headers, json=payload).status_code == 403
    assert client.post(url, headers=w.ops.headers, json={"points": []}).status_code == 422
    first = client.post(url, headers=w.ops.headers, json=payload)
    assert first.status_code == 200, first.text
    assert first.json() == {point_id: "accepted"}
    duplicate = client.post(url, headers=w.ops.headers, json=payload)
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json() == {point_id: "duplicate"}
    stop = client.post(f"{API}/me/gps/shares/{share['phone_share_id']}/stop", headers=w.ops.headers)
    assert stop.status_code == 204
    assert client.post(url, headers=w.ops.headers, json=payload).status_code == 409
