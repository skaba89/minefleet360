"""Lecture des preuves de compteur, sans supposer un cumul fiable.

Les relevés bruts ne prouvent pas à eux seuls la distance ou les heures
cumulées depuis le dernier entretien, particulièrement après un reset.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.fleet.models import VehicleMeterReading


@dataclass(frozen=True)
class MeterEvidence:
    latest_value: Decimal | None
    latest_read_at: datetime | None
    has_reset: bool
    cumulative_verified: bool = False


def meter_readings_query(
    tenant_id: uuid.UUID, vehicle_id: uuid.UUID, meter_kind: str
) -> Select[VehicleMeterReading]:
    return (
        select(VehicleMeterReading)
        .where(
            VehicleMeterReading.tenant_id == tenant_id,
            VehicleMeterReading.vehicle_id == vehicle_id,
            VehicleMeterReading.meter_kind == meter_kind,
        )
        .order_by(VehicleMeterReading.read_at.desc(), VehicleMeterReading.vehicle_meter_reading_id.desc())
    )


def inspect_meter_evidence(
    db: Session, tenant_id: uuid.UUID, vehicle_id: uuid.UUID, meter_kind: str
) -> MeterEvidence:
    """Conserver les relevés bruts à titre de preuve ; ne jamais les certifier cumulés."""
    rows = list(db.scalars(meter_readings_query(tenant_id, vehicle_id, meter_kind)))
    if not rows:
        return MeterEvidence(latest_value=None, latest_read_at=None, has_reset=False)
    latest = rows[0]
    return MeterEvidence(
        latest_value=latest.value,
        latest_read_at=latest.read_at,
        has_reset=any(row.reset_reason is not None for row in rows),
    )
