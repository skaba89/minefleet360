"""Exercise registry services with the existing PostgreSQL test harness."""

import uuid

import pytest
from sqlalchemy import select

from app.audit.models import AuditEvent
from app.authz.dependencies import Authorized
from app.authz.principal import PermissionScope, Principal
from app.cli import change_iot_entitlement
from app.core.clock import SystemClock
from app.core.db import new_session
from app.core.errors import AppError
from app.core.tenancy import set_tenant_context
from app.iot.schemas import GatewayCreate, ManufacturerCreate, SensorCreate
from app.iot.service import create_gateway, create_manufacturer, create_sensor
from tests.conftest import Api


def test_registry_service_scope_and_audit(api: Api) -> None:
    tenant = api.tenant()
    other = api.tenant()
    assert change_iot_entitlement(tenant.tenant_id, True, "Test registry", True) == 0
    principal = Principal(
        user_id=tenant.admin.user_id,
        tenant_id=tenant.tenant_id,
        tenant_kind="CUSTOMER",
        session_id=uuid.uuid4(),
        grants=(),
    )
    full = PermissionScope("iot.registry.manage", True, frozenset(), frozenset({"TENANT_ADMIN"}))
    local = PermissionScope(
        "iot.registry.manage", False, frozenset({tenant.sites["S1"]}), frozenset({"OPS_MANAGER"})
    )
    with new_session() as db:
        auth = Authorized(principal, full, db, SystemClock())
        scoped = Authorized(principal, local, db, SystemClock())
        set_tenant_context(db, tenant.tenant_id)
        with pytest.raises(AppError):
            create_manufacturer(scoped, ManufacturerCreate(name="Denied"))
        manufacturer = create_manufacturer(auth, ManufacturerCreate(name="Demo OEM"))
        set_tenant_context(db, tenant.tenant_id)
        body = GatewayCreate(
            site_id=tenant.sites["S1"],
            manufacturer_id=manufacturer.manufacturer_id,
            external_id="G1",
            model="Demo",
            source_kind="SIMULATED",
        )
        gateway = create_gateway(scoped, body)
        set_tenant_context(db, tenant.tenant_id)
        for site_id in (tenant.sites["S2"], other.sites["S1"]):
            with pytest.raises(AppError):
                create_gateway(scoped, body.model_copy(update={"site_id": site_id}))
        sensor_body = SensorCreate(
            gateway_id=gateway.gateway_id,
            manufacturer_id=manufacturer.manufacturer_id,
            external_id="S1",
            model="Demo",
            sensor_kind="TPMS",
        )
        with pytest.raises(AppError):
            create_sensor(scoped, sensor_body.model_copy(update={"gateway_id": uuid.uuid4()}))
        sensor = create_sensor(scoped, sensor_body)
        assert sensor.site_id == gateway.site_id
        assert sensor.source_kind == gateway.source_kind
        set_tenant_context(db, tenant.tenant_id)
        actions = db.scalars(
            select(AuditEvent.action).where(
                AuditEvent.entity_id.in_([manufacturer.manufacturer_id, gateway.gateway_id, sensor.sensor_id])
            )
        ).all()
        assert set(actions) == {"iot.manufacturer.create", "iot.gateway.create", "iot.sensor.create"}
