"""Integration tests for the privileged IoT entitlement CLI."""

import uuid

from sqlalchemy import text

from app.cli import main
from app.core.db import new_session
from app.core.tenancy import PLATFORM_TENANT_ID, set_tenant_context
from app.iot.entitlement import provisioning_enabled
from tests.conftest import Api


def test_audited_entitlement_cli(api: Api) -> None:
    first = api.tenant()
    second = api.tenant()
    args = ["iot-entitlement", "--tenant-id", str(first.tenant_id), "--reason", "Test contract"]

    def state() -> tuple[bool, int]:
        with new_session() as db:
            set_tenant_context(db, first.tenant_id)
            enabled = provisioning_enabled(db, first.tenant_id)
            count = db.execute(
                text("SELECT count(*) FROM audit_event WHERE action = 'iot.entitlement.change'")
            ).scalar_one()
            return enabled, count

    assert main([*args, "--enable"]) == 0
    assert state() == (False, 0)
    assert main([*args, "--enable", "--apply"]) == 0
    assert state() == (True, 1)
    assert main([*args, "--enable", "--apply"]) == 0
    assert state() == (True, 1)
    with new_session() as db:
        set_tenant_context(db, second.tenant_id)
        assert provisioning_enabled(db, second.tenant_id) is False
        assert provisioning_enabled(db, first.tenant_id) is False
    assert main([*args, "--disable", "--apply"]) == 0
    assert state() == (False, 2)
    for invalid in (uuid.uuid4(), PLATFORM_TENANT_ID):
        assert main(["iot-entitlement", "--tenant-id", str(invalid), "--enable", "--reason", "Test"]) == 3
