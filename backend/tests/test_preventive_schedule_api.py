"""Contrat HTTP minimal du déclenchement d'une maintenance préventive."""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import API
from tests.test_assignment import World, w  # noqa: F401


def test_preventive_schedule_requires_authentication(client: TestClient) -> None:
    response = client.post(f"{API}/preventive-dues/{uuid.uuid4()}/schedule")
    assert response.status_code == 401


def test_preventive_schedule_unknown_due_returns_not_found(
    client: TestClient,
    w: World,  # noqa: F811
) -> None:
    response = client.post(
        f"{API}/preventive-dues/{uuid.uuid4()}/schedule",
        headers=w.ops.headers,
    )
    assert response.status_code == 404, response.text


def test_preventive_schedule_rejects_role_without_permission(
    client: TestClient,
    w: World,  # noqa: F811
) -> None:
    response = client.post(
        f"{API}/preventive-dues/{uuid.uuid4()}/schedule",
        headers=w.dispatcher.headers,
    )
    assert response.status_code == 403, response.text
