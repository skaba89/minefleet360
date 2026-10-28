"""Concurrence réelle du service de création d'OT préventifs sur PostgreSQL."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.authz.dependencies import Authorized
from app.authz.principal import Grant, PermissionScope, Principal
from app.core.clock import SystemClock
from app.core.config import get_settings
from app.core.tenancy import set_tenant_context
from app.maintenance import preventive_schedule
from app.maintenance.schemas import WorkOrderCreate, WorkOrderOut
from tests.conftest import API
from tests.test_assignment import World, _vehicle, w  # noqa: F401


def test_two_concurrent_schedule_calls_return_one_work_order(
    client: TestClient,
    w: World,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deux sessions concurrentes créent un seul OT, lié à une seule échéance."""
    vehicle_id = _vehicle(client, w)
    response = client.post(
        f"{API}/preventive-plans",
        headers=w.ops.headers,
        json={"vehicle_id": vehicle_id, "code": "OT-RACE-27", "days_interval": 30},
    )
    assert response.status_code == 201, response.text

    tenant_id = w.t.tenant_id
    due_id = uuid.uuid4()
    engine = create_engine(get_settings().database_url(), pool_size=3, max_overflow=0)
    sessions = sessionmaker(bind=engine)
    entered_creation = threading.Event()
    release_creation = threading.Event()
    original = preventive_schedule._create_work_order_uncommitted

    def slow_creation(auth: Authorized, body: WorkOrderCreate) -> WorkOrderOut:
        entered_creation.set()
        assert release_creation.wait(timeout=15), "first transaction was not released"
        return original(auth, body)

    monkeypatch.setattr(preventive_schedule, "_create_work_order_uncommitted", slow_creation)

    principal = Principal(
        user_id=w.ops.user_id,
        tenant_id=tenant_id,
        tenant_kind="CUSTOMER",
        session_id=uuid.uuid4(),
        grants=(Grant("OPS_MANAGER", "TENANT", None),),
    )
    scope = PermissionScope(
        permission="maintenance.preventive.manage",
        tenant_wide=True,
        site_ids=frozenset(),
        roles=frozenset({"OPS_MANAGER"}),
        role_grants=frozenset({("OPS_MANAGER", None)}),
    )

    def schedule() -> uuid.UUID:
        with sessions() as db:
            set_tenant_context(db, tenant_id)
            auth = Authorized(principal=principal, scope=scope, db=db, clock=SystemClock())
            return preventive_schedule.schedule_preventive_order(auth, due_id)

    try:
        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(tenant_id)},
            )
            conn.execute(
                text(
                    "INSERT INTO maintenance_due "
                    "(maintenance_due_id, tenant_id, maintenance_plan_id, vehicle_id, "
                    "trigger_kind, trigger_key, due_on, status) VALUES "
                    "(:due, :tenant, :plan, :vehicle, 'DAYS', 'DAYS:OT-RACE-27', :day, 'DUE')"
                ),
                {
                    "due": str(due_id),
                    "tenant": str(tenant_id),
                    "plan": response.json()["maintenance_plan_id"],
                    "vehicle": vehicle_id,
                    "day": date(2026, 12, 27),
                },
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(schedule)
            try:
                assert entered_creation.wait(timeout=15)
                second = pool.submit(schedule)
            finally:
                release_creation.set()
            first_id = first.result(timeout=30)
            second_id = second.result(timeout=30)

        assert first_id == second_id
        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(tenant_id)},
            )
            row = conn.execute(
                text(
                    "SELECT status, work_order_id FROM maintenance_due "
                    "WHERE maintenance_due_id = :due"
                ),
                {"due": str(due_id)},
            ).one()
            assert row.status == "SCHEDULED"
            assert row.work_order_id == first_id
            count = conn.execute(
                text(
                    "SELECT count(*) FROM work_order WHERE tenant_id = :tenant "
                    "AND work_order_id = :order_id"
                ),
                {"tenant": str(tenant_id), "order_id": str(first_id)},
            ).scalar_one()
            assert count == 1
    finally:
        release_creation.set()
        engine.dispose()
