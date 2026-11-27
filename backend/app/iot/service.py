"""Registry operations guarded by commercial entitlement and HTTP permissions."""

import uuid

from sqlalchemy import select, text

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.iot.entitlement import provisioning_enabled
from app.iot.models import IoTGateway, IoTManufacturer, IoTSensor
from app.iot.schemas import (
    GatewayCreate,
    GatewayOut,
    ManufacturerCreate,
    ManufacturerOut,
    SensorCreate,
    SensorOut,
)
from app.organization.contracts import active_site_in_scope


def _require_customer(auth: Authorized) -> None:
    if auth.principal.tenant_kind != "CUSTOMER":
        raise AppError("PERMISSION_DENIED")


def _require_provisioning(auth: Authorized) -> None:
    # Same transaction lock as the administration CLI; no create can race a revocation.
    auth.db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended('iot.entitlement:' || :key, 0))"),
        {"key": str(auth.tenant_id)},
    )
    if not provisioning_enabled(auth.db, auth.tenant_id):
        raise AppError("PERMISSION_DENIED", message_fr="Le provisionnement IoT n'est pas activé.")


def _manufacturer(auth: Authorized, manufacturer_id: uuid.UUID) -> IoTManufacturer:
    item = auth.db.scalar(
        select(IoTManufacturer).where(
            IoTManufacturer.tenant_id == auth.tenant_id,
            IoTManufacturer.manufacturer_id == manufacturer_id,
        )
    )
    if item is None:
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "manufacturer_id"}])
    return item


def _active_site(auth: Authorized, site_id: uuid.UUID) -> None:
    site = active_site_in_scope(auth.db, auth.scope, site_id)
    if site is None or site.tenant_id != auth.tenant_id:
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "site_id"}])


def _audit(auth: Authorized, entity: str, entity_id: uuid.UUID, site_id: uuid.UUID | None = None) -> None:
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action=f"iot.{entity}.create",
        entity_type=f"iot_{entity}",
        entity_id=entity_id,
        site_id=site_id,
    )


def create_manufacturer(auth: Authorized, body: ManufacturerCreate) -> ManufacturerOut:
    _require_customer(auth)
    if not auth.scope.tenant_wide:
        raise AppError("PERMISSION_DENIED")
    _require_provisioning(auth)
    item = IoTManufacturer(tenant_id=auth.tenant_id, name=body.name)
    auth.db.add(item)
    auth.db.flush()
    _audit(auth, "manufacturer", item.manufacturer_id)
    result = ManufacturerOut.model_validate(item)
    auth.db.commit()
    return result


def create_gateway(auth: Authorized, body: GatewayCreate) -> GatewayOut:
    _require_customer(auth)
    _require_provisioning(auth)
    _active_site(auth, body.site_id)
    _manufacturer(auth, body.manufacturer_id)
    item = IoTGateway(tenant_id=auth.tenant_id, **body.model_dump())
    auth.db.add(item)
    auth.db.flush()
    _audit(auth, "gateway", item.gateway_id, item.site_id)
    result = GatewayOut.model_validate(item)
    auth.db.commit()
    return result


def create_sensor(auth: Authorized, body: SensorCreate) -> SensorOut:
    _require_customer(auth)
    _require_provisioning(auth)
    gateway = auth.db.scalar(
        select(IoTGateway).where(
            IoTGateway.tenant_id == auth.tenant_id,
            IoTGateway.gateway_id == body.gateway_id,
        )
    )
    if gateway is None or not auth.scope.covers_site(gateway.site_id) or gateway.status != "REGISTERED":
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "gateway_id"}])
    _active_site(auth, gateway.site_id)
    _manufacturer(auth, body.manufacturer_id)
    item = IoTSensor(
        tenant_id=auth.tenant_id,
        site_id=gateway.site_id,
        source_kind=gateway.source_kind,
        **body.model_dump(),
    )
    auth.db.add(item)
    auth.db.flush()
    _audit(auth, "sensor", item.sensor_id, item.site_id)
    result = SensorOut.model_validate(item)
    auth.db.commit()
    return result
