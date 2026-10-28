"""Intégration PostgreSQL réelle : unicité des échéances et isolation RLS."""

import uuid
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401 (fixture w)


def test_due_insert_is_idempotent_and_invisible_from_other_tenant(
    client: TestClient,
    w: World,  # noqa: F811 (fixture w)
    api: Api,
) -> None:
    vehicle_id = _vehicle(client, w)
    created = client.post(
        f"{API}/preventive-plans",
        headers=w.ops.headers,
        json={"vehicle_id": vehicle_id, "code": "CHECK-30", "days_interval": 30},
    )
    assert created.status_code == 201, created.text
    plan_id = created.json()["maintenance_plan_id"]
    outsider = api.tenant(sites=())
    due_id = uuid.uuid4()
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    sql = text(
        """
        INSERT INTO maintenance_due (
            maintenance_due_id, tenant_id, maintenance_plan_id, vehicle_id,
            trigger_kind, trigger_key, due_on, status
        ) VALUES (
            :due_id, :tenant_id, :plan_id, :vehicle_id,
            'DAYS', 'DAYS:2026-01-01', :due_on, 'DUE'
        )
        ON CONFLICT ON CONSTRAINT uq_maintenance_due_idempotence DO NOTHING
        RETURNING maintenance_due_id
        """
    )
    params = {
        "due_id": str(due_id),
        "tenant_id": str(w.t.tenant_id),
        "plan_id": plan_id,
        "vehicle_id": vehicle_id,
        "due_on": date(2026, 1, 31),
    }
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(w.t.tenant_id)})
            assert conn.execute(sql, params).scalar_one() == due_id
            assert conn.execute(sql, params).scalar_one_or_none() is None
            count = conn.execute(
                text("SELECT count(*) FROM maintenance_due WHERE maintenance_plan_id = :pid"),
                {"pid": plan_id},
            ).scalar_one()
            assert count == 1
        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": str(outsider.tenant_id)},
            )
            count = conn.execute(
                text("SELECT count(*) FROM maintenance_due WHERE maintenance_due_id = :id"),
                {"id": str(due_id)},
            ).scalar_one()
            assert count == 0
    finally:
        engine.dispose()
