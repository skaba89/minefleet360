from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.ratelimit import FailureLimiter
from app.core.request_context import get_request_meta
from app.core.security import CompositeToken
from app.core.tenancy import set_tenant_context
from app.fleet.gps_authenticated_device import resolve_authenticated_gps_device
from app.fleet.gps_binding_models import FleetGpsDeviceBinding
from app.fleet.gps_gateway_ingestion import TrustedGatewayContext
from app.fleet.gps_payload_ingestion import (
    accept_gps_telemetry_payload,
    decode_gps_telemetry,
)
from app.fleet.models import Vehicle
from app.organization.models import Tenant


def check_source_rate(now: datetime) -> None:
    meta = get_request_meta()
    key = f"gps-source:{meta.ip_address if meta else 'unknown'}"
    limiter = FailureLimiter("source", 1000, timedelta(minutes=1))
    if limiter.is_blocked(key, now):
        raise AppError("RATE_LIMITED", headers={"Retry-After": "60"})
    limiter.record_failure(key, now)


def ingest_tracker(db: Session, credential: CompositeToken, payload: bytes, now: datetime) -> None:
    # Le tenant du jeton opaque est seulement un sélecteur RLS jusqu'à vérification de son secret.
    # Aucune écriture ni réponse de données n'est autorisée à cette étape.
    set_tenant_context(db, credential.tenant_id)
    binding = db.scalar(
        select(FleetGpsDeviceBinding)
        .where(
            FleetGpsDeviceBinding.tenant_id == credential.tenant_id,
            FleetGpsDeviceBinding.gps_device_binding_id == credential.record_id,
            FleetGpsDeviceBinding.revoked_at.is_(None),
        )
        .execution_options(populate_existing=True)
    )
    trusted = resolve_authenticated_gps_device(
        db,
        trusted_tenant_id=credential.tenant_id,
        device_id=binding.device_id if binding is not None else "",
        supplied_secret=credential.secret,
        at=now,
    )
    if binding is None or trusted is None:
        raise AppError("AUTH_REQUIRED")
    vehicle = db.scalar(
        select(Vehicle)
        .where(
            Vehicle.tenant_id == trusted.tenant_id,
            Vehicle.vehicle_id == trusted.vehicle_id,
            Vehicle.site_id == trusted.site_id,
            Vehicle.status != "RETIRED",
        )
        .with_for_update()
    )
    # Même ordre de verrouillage que le provisionnement/révocation : véhicule puis liaison.
    locked = db.scalar(
        select(FleetGpsDeviceBinding)
        .where(
            FleetGpsDeviceBinding.tenant_id == credential.tenant_id,
            FleetGpsDeviceBinding.gps_device_binding_id == credential.record_id,
            FleetGpsDeviceBinding.revoked_at.is_(None),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        locked is None
        or resolve_authenticated_gps_device(
            db,
            trusted_tenant_id=credential.tenant_id,
            device_id=locked.device_id,
            supplied_secret=credential.secret,
            at=now,
        )
        is None
    ):
        raise AppError("AUTH_REQUIRED")
    tenant = db.scalar(select(Tenant).where(Tenant.tenant_id == trusted.tenant_id, Tenant.status == "ACTIVE"))
    if vehicle is None or tenant is None:
        raise AppError("AUTH_REQUIRED")
    device_limiter = FailureLimiter("tokens", 60, timedelta(minutes=1))
    key = f"gps-binding:{credential.tenant_id}:{credential.record_id}"
    if device_limiter.is_blocked(key, now):
        raise AppError("RATE_LIMITED", headers={"Retry-After": "60"})
    device_limiter.record_failure(key, now)
    message = decode_gps_telemetry(payload)
    if message.device_id != binding.device_id:
        raise AppError("AUTH_REQUIRED")
    accepted = accept_gps_telemetry_payload(
        db,
        context=TrustedGatewayContext(trusted.tenant_id),
        payload=bytes(payload),
        supplied_secret=credential.secret,
        received_at=now,
    )
    if not accepted:
        raise AppError("CONFLICT", message_fr="Message GPS refusé, ancien ou déjà reçu.")
    db.commit()
