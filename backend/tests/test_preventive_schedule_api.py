"""Contrat HTTP minimal du déclenchement d'une maintenance préventive."""

import uuid
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from tests.conftest import API
from tests.test_assignment import World, _vehicle, w  # noqa: F401


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


def test_schedule_due_http_creates_and_replays_same_order(
    client: TestClient,
    w: World,  # noqa: F811
) -> None:
    """Le POST crée un OT préventif ; le second POST reste idempotent."""
    vehicle_id = _vehicle(client, w)
    created = client.post(
        f"{API}/preventive-plans",
        headers=w.ops.headers,
        json={"vehicle_id": vehicle_id, "code": "API-SCHEDULE-29", "days_interval": 30},
    )
    assert created.status_code == 201, created.text

    due_id = uuid.uuid4()
    engine = create_engine(get_settings().database_url())
    try:
        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(w.t.tenant_id)},
            )
            conn.execute(
                text(
                    "INSERT INTO maintenance_due "
                    "(maintenance_due_id, tenant_id, maintenance_plan_id, vehicle_id, "
                    "trigger_kind, trigger_key, due_on, status) VALUES "
                    "(:due, :tenant, :plan, :vehicle, 'DAYS', 'DAYS:API-29', :day, 'DUE')"
                ),
                {
                    "due": str(due_id),
                    "tenant": str(w.t.tenant_id),
                    "plan": created.json()["maintenance_plan_id"],
                    "vehicle": vehicle_id,
                    "day": date(2026, 12, 29),
                },
            )

        url = f"{API}/preventive-dues/{due_id}/schedule"
        first = client.post(url, headers=w.ops.headers)
        assert first.status_code == 200, first.text
        second = client.post(url, headers=w.ops.headers)
        assert second.status_code == 200, second.text
        assert first.json() == second.json()
        order_id = first.json()["work_order_id"]

        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(w.t.tenant_id)},
            )
            row = conn.execute(
                text("SELECT status, work_order_id FROM maintenance_due WHERE maintenance_due_id = :due"),
                {"due": str(due_id)},
            ).one()
            assert row.status == "SCHEDULED"
            assert str(row.work_order_id) == order_id
            count = conn.execute(
                text("SELECT count(*) FROM work_order WHERE work_order_id = :id AND kind = 'PREVENTIVE'"),
                {"id": order_id},
            ).scalar_one()
            assert count == 1
    finally:
        engine.dispose()
