"""Résoudre une association GPS active depuis la base sous contexte tenant RLS.

Ce module ne permet pas d'authentifier un traceur : le tenant est fourni
par une passerelle déjà authentifiée, jamais par une charge utile non fiable.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fleet.gps_binding_models import FleetGpsDeviceBinding
from app.fleet.gps_device_binding import GpsDeviceBinding, device_matches_binding


def resolve_gps_binding(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    site_id: uuid.UUID,
    device_id: str,
    recorded_at: datetime,
) -> FleetGpsDeviceBinding | None:
    """Refuser toute association absente, révoquée ou incohérente."""
    if not device_id or not device_id.strip() or recorded_at.tzinfo is None:
        return None
    candidate = db.execute(
        select(FleetGpsDeviceBinding)
        .where(
            FleetGpsDeviceBinding.tenant_id == tenant_id,
            FleetGpsDeviceBinding.device_id == device_id,
            FleetGpsDeviceBinding.vehicle_id == vehicle_id,
            FleetGpsDeviceBinding.site_id == site_id,
            FleetGpsDeviceBinding.active_from <= recorded_at,
        )
        .order_by(FleetGpsDeviceBinding.active_from.desc())
        .limit(1)
    ).scalar_one_or_none()
    if candidate is None:
        return None
    binding = GpsDeviceBinding(
        tenant_id=candidate.tenant_id,
        vehicle_id=candidate.vehicle_id,
        site_id=candidate.site_id,
        device_id=candidate.device_id,
        active_from=candidate.active_from,
        revoked_at=candidate.revoked_at,
    )
    if not device_matches_binding(
        binding,
        tenant_id=tenant_id,
        vehicle_id=vehicle_id,
        site_id=site_id,
        device_id=device_id,
        recorded_at=recorded_at,
    ):
        return None
    return candidate
