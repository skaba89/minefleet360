"""Concurrence réelle : une échéance ne peut être insérée deux fois.

Deux transactions PostgreSQL distinctes démarrent le même INSERT.
Ce test complète les contrats unitaires et l'isolation RLS du lot 3b.17.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from tests.conftest import API
from tests.test_assignment import World, _vehicle, w  # noqa: F401 (fixture w)


def test_concurrent_due_insert_creates_only_one_row(
    client: TestClient,
    w: World,  # noqa: F811 (fixture w)
) -> None:
    vehicle_id = _vehicle(client, w)
    plan = client.post(
        f"{API}/preventive-plans",
        headers=w.ops.headers,
        json={"vehicle_id": vehicle_id, "code": "CONCURRENT-30", "days_interval": 30},
    )
    assert plan.status_code == 201, plan.text
    plan_id = plan.json()["maintenance_plan_id"]
    barrier = threading.Barrier(2)
    engine = create_engine(
        get_settings().database_url(),
        pool_size=2,
        max_overflow=0,
        connect_args={"options": "-c lock_timeout=15000"},
    )
    stmt = text(
        """
        INSERT INTO maintenance_due (
            tenant_id, maintenance_plan_id, vehicle_id,
            trigger_kind, trigger_key, due_on, status
        ) VALUES (
            :tenant_id, :plan_id, :vehicle_id,
            'DAYS', 'DAYS:2026-01-01', :due_on, 'DUE'
        )
        ON CONFLICT ON CONSTRAINT uq_maintenance_due_idempotence DO NOTHING
        RETURNING maintenance_due_id
        """
    )
    params = {
        "tenant_id": str(w.t.tenant_id),
        "plan_id": plan_id,
        "vehicle_id": vehicle_id,
        "due_on": date(2026, 1, 31),
    }

    def insert_once() -> uuid.UUID | None:
        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": str(w.t.tenant_id)},
            )
            barrier.wait(timeout=10)
            result = conn.execute(stmt, params).scalar_one_or_none()
            return result if isinstance(result, uuid.UUID) or result is None else uuid.UUID(str(result))

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(insert_once)
            second = executor.submit(insert_once)
            results = (first.result(timeout=30), second.result(timeout=30))
        assert sum(value is not None for value in results) == 1
        assert sum(value is None for value in results) == 1

        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": str(w.t.tenant_id)},
            )
            total = conn.execute(
                text("SELECT count(*) FROM maintenance_due WHERE maintenance_plan_id = :pid"),
                {"pid": plan_id},
            ).scalar_one()
            assert total == 1
    finally:
        engine.dispose()
