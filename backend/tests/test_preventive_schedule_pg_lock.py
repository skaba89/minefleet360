"""Test PostgreSQL réel du verrou de ligne sur une échéance préventive.

Deux connexions indépendantes : la seconde ne peut verrouiller la même
échéance pendant que la première détient FOR UPDATE. Aucun OT n'est créé ici.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from tests.conftest import API
from tests.test_assignment import World, _vehicle, w  # noqa: F401


def test_preventive_due_row_lock_blocks_competing_transaction(
    client: TestClient,
    w: World,  # noqa: F811
) -> None:
    vehicle_id = _vehicle(client, w)
    response = client.post(
        f"{API}/preventive-plans",
        headers=w.ops.headers,
        json={"vehicle_id": vehicle_id, "code": "LOCK-TEST", "days_interval": 30},
    )
    assert response.status_code == 201, response.text

    engine = create_engine(get_settings().database_url(), pool_size=2, max_overflow=0)
    due_id = uuid.uuid4()
    params = {
        "tenant_id": str(w.t.tenant_id),
        "plan_id": response.json()["maintenance_plan_id"],
        "vehicle_id": vehicle_id,
        "due_id": str(due_id),
    }
    locked = threading.Event()
    release = threading.Event()

    def set_tenant(conn: Connection) -> None:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": params["tenant_id"]},
        )

    def hold_lock() -> None:
        with engine.begin() as conn:
            set_tenant(conn)
            result = conn.execute(
                text(
                    "SELECT maintenance_due_id FROM maintenance_due "
                    "WHERE maintenance_due_id = :due_id FOR UPDATE"
                ),
                {"due_id": params["due_id"]},
            ).scalar_one()
            assert str(result) == params["due_id"]
            locked.set()
            assert release.wait(timeout=15), "competing transaction did not finish"

    try:
        with engine.begin() as conn:
            set_tenant(conn)
            conn.execute(
                text(
                    "INSERT INTO maintenance_due "
                    "(maintenance_due_id, tenant_id, maintenance_plan_id, vehicle_id, "
                    "trigger_kind, trigger_key, due_on, status) VALUES "
                    "(:due_id, :tenant_id, :plan_id, :vehicle_id, "
                    "'DAYS', 'DAYS:LOCK-TEST', :due_on, 'DUE')"
                ),
                {**params, "due_on": date(2026, 12, 1)},
            )

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(hold_lock)
            assert locked.wait(timeout=15), "first transaction failed to acquire lock"
            try:
                with pytest.raises(OperationalError) as error:
                    with engine.begin() as conn:
                        set_tenant(conn)
                        conn.execute(
                            text(
                                "SELECT maintenance_due_id FROM maintenance_due "
                                "WHERE maintenance_due_id = :due_id FOR UPDATE NOWAIT"
                            ),
                            {"due_id": params["due_id"]},
                        ).scalar_one()
                assert error.value.orig.sqlstate == "55P03"
            finally:
                release.set()
            future.result(timeout=15)

        with engine.begin() as conn:
            set_tenant(conn)
            result = conn.execute(
                text(
                    "SELECT maintenance_due_id FROM maintenance_due "
                    "WHERE maintenance_due_id = :due_id FOR UPDATE NOWAIT"
                ),
                {"due_id": params["due_id"]},
            ).scalar_one()
            assert str(result) == params["due_id"]
    finally:
        release.set()
        engine.dispose()
