"""Owner administration remains scoped and unavailable to the application role."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from app.core.db import new_session
from app.core.tenancy import set_tenant_context
from app.iot.entitlement import provisioning_enabled
from tests.conftest import Api


def test_owner_activation_and_isolation(api: Api) -> None:
    first = api.tenant()
    second = api.tenant()
    engine = create_engine(get_settings().database_url(owner=True), pool_size=1, max_overflow=0)
    context = text("SELECT set_config('app.tenant_id', :t, true)")
    insert = text("INSERT INTO iot_entitlement (tenant_id, provisioning_enabled) VALUES (:t, true)")
    try:
        with engine.begin() as conn:
            conn.execute(context, {"t": str(first.tenant_id)})
            conn.execute(insert, {"t": first.tenant_id})
            with pytest.raises(DBAPIError) as error:
                with conn.begin_nested():
                    conn.execute(insert, {"t": second.tenant_id})
            assert getattr(error.value.orig, "sqlstate", None) == "42501"

        with new_session() as db:
            set_tenant_context(db, first.tenant_id)
            assert provisioning_enabled(db, first.tenant_id) is True
            set_tenant_context(db, second.tenant_id)
            assert provisioning_enabled(db, first.tenant_id) is False
            assert provisioning_enabled(db, second.tenant_id) is False

        with engine.begin() as conn:
            conn.execute(context, {"t": str(second.tenant_id)})
            assert conn.execute(text("SELECT count(*) FROM iot_entitlement")).scalar_one() == 0
            conn.execute(context, {"t": str(first.tenant_id)})
            conn.execute(
                text("UPDATE iot_entitlement SET provisioning_enabled = false WHERE tenant_id = :t"),
                {"t": first.tenant_id},
            )

        with new_session() as db:
            set_tenant_context(db, first.tenant_id)
            assert provisioning_enabled(db, first.tenant_id) is False
    finally:
        engine.dispose()
