"""Concurrence réelle sur la transition d'état d'une échéance préventive.

Deux transactions PostgreSQL tentent le même passage DUE -> SCHEDULED.
Le verrou FOR UPDATE garantit que la seconde relit le statut validé
par la première et ne répète pas la transition. Aucun OT n'est créé.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from tests.conftest import API
from tests.test_assignment import World, _vehicle, w  # noqa: F401


def test_competing_due_status_transitions_only_one_wins(
    client: TestClient,
    w: World,  # noqa: F811
) -> None:
    vehicle_id = _vehicle(client, w)
    response = client.post(
        f"{API}/preventive-plans",
        headers=w.ops.headers,
        json={"vehicle_id": vehicle_id, "code": "RACE-TRANSITION", "days_interval": 30},
    )
    assert response.status_code == 201, response.text

    tenant_id = str(w.t.tenant_id)
    due_id = str(uuid.uuid4())
    engine = create_engine(get_settings().database_url(), pool_size=2, max_overflow=0)
    first_locked = threading.Event()
    allow_first_commit = threading.Event()

    def set_tenant(conn: Connection) -> None:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )

    def transition(hold: bool) -> bool:
        with engine.begin() as conn:
            set_tenant(conn)
            status = conn.execute(
                text(
                    "SELECT status FROM maintenance_due "
                    "WHERE maintenance_due_id = :due_id FOR UPDATE"
                ),
                {"due_id": due_id},
            ).scalar_one()
            if hold:
                first_locked.set()
                assert allow_first_commit.wait(timeout=15)
            if status != "DUE":
                return False
            conn.execute(
                text(
                    "UPDATE maintenance_due SET status = 'SCHEDULED' "
                    "WHERE maintenance_due_id = :due_id"
                ),
                {"due_id": due_id},
            )
            return True

    try:
        with engine.begin() as conn:
            set_tenant(conn)
            conn.execute(
                text(
                    "INSERT INTO maintenance_due "
                    "(maintenance_due_id, tenant_id, maintenance_plan_id, vehicle_id, "
                    "trigger_kind, trigger_key, due_on, status) VALUES "
                    "(:due_id, :tenant_id, :plan_id, :vehicle_id, "
                    "'DAYS', 'DAYS:RACE-TRANSITION', :due_on, 'DUE')"
                ),
                {
                    "due_id": due_id,
                    "tenant_id": tenant_id,
                    "plan_id": response.json()["maintenance_plan_id"],
                    "vehicle_id": vehicle_id,
                    "due_on": date(2026, 12, 2),
                },
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(transition, True)
            assert first_locked.wait(timeout=15)
            second = pool.submit(transition, False)
            allow_first_commit.set()
            results = [first.result(timeout=20), second.result(timeout=20)]
        assert results == [True, False]

        with engine.begin() as conn:
            set_tenant(conn)
            status = conn.execute(
                text("SELECT status FROM maintenance_due WHERE maintenance_due_id = :due_id"),
                {"due_id": due_id},
            ).scalar_one()
            assert status == "SCHEDULED"
    finally:
        allow_first_commit.set()
        engine.dispose()
