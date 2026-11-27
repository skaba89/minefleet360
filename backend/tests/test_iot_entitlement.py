"""Database contract for the read-only IoT provisioning entitlement."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from app.core.db import new_session
from app.core.tenancy import set_tenant_context
from app.iot.entitlement import provisioning_enabled
from tests.conftest import Api


def test_entitlement_is_disabled_and_read_only(api: Api) -> None:
    first = api.tenant()
    second = api.tenant()
    with new_session() as db:
        for tenant in (first, second):
            set_tenant_context(db, tenant.tenant_id)
            assert provisioning_enabled(db, tenant.tenant_id) is False
        db.rollback()

    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(first.tenant_id)})
            for sql in (
                "INSERT INTO iot_entitlement (tenant_id, provisioning_enabled) VALUES (:t, true)",
                "UPDATE iot_entitlement SET provisioning_enabled = true WHERE tenant_id = :t",
                "DELETE FROM iot_entitlement WHERE tenant_id = :t",
            ):
                with pytest.raises(DBAPIError) as error:
                    with conn.begin_nested():
                        conn.execute(text(sql), {"t": first.tenant_id})
                assert getattr(error.value.orig, "sqlstate", None) == "42501"
            assert conn.execute(text("SELECT count(*) FROM iot_entitlement")).scalar_one() == 0
    finally:
        engine.dispose()
