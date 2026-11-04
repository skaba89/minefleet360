"""Cumul d'un compteur à la clôture d'un entretien préventif, sans approbation manuelle.

Règle (docs/PREVENTIVE_DUES.md, décision du 3 novembre 2026) :
1. cumul au jalon validé **précédent** + hausses des relevés bruts jusqu'à la clôture, si le
   compteur est fiable ;
2. sinon (entretien initial sans cumul de départ, ou baisse constatée depuis le jalon), le
   **dernier relevé brut** au plus tard à la clôture devient la nouvelle référence. C'est prudent :
   les km ou heures parcourus entre ce relevé et la clôture sont comptés dans le cycle suivant, ce
   qui avance l'échéance suivante sans jamais la retarder ;
3. sans aucun relevé : None (la finalisation est refusée et demande un relevé).
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fleet.models import VehicleMeterReading
from app.maintenance.preventive_baseline_read import load_verified_service_baseline
from app.maintenance.preventive_meters_since import KIND_HOURS, KIND_KM, meters_since_anchor


def closure_totals(
    db: Session, tenant_id: uuid.UUID, vehicle_id: uuid.UUID, plan_code: str, closed_at: datetime
) -> dict[str, Decimal | None]:
    """Cumul de clôture par compteur ; le jalon exclut l'OT clôturé lui-même (instant antérieur)."""
    baseline = load_verified_service_baseline(
        db, tenant_id, vehicle_id, plan_code=plan_code, as_of=closed_at - timedelta(microseconds=1)
    )
    meters = meters_since_anchor(
        db,
        tenant_id,
        vehicle_id,
        anchor_at=baseline.anchor_at,
        anchor_km=baseline.cumulative_km,
        anchor_hours=baseline.cumulative_hours,
        as_of=closed_at,
    )
    computed = {KIND_KM: meters.cumulative_km, KIND_HOURS: meters.cumulative_hours}
    out: dict[str, Decimal | None] = {}
    for kind, value in computed.items():
        out[kind] = value if value is not None else _last_reading(db, tenant_id, vehicle_id, kind, closed_at)
    return out


def _last_reading(
    db: Session, tenant_id: uuid.UUID, vehicle_id: uuid.UUID, kind: str, closed_at: datetime
) -> Decimal | None:
    return db.execute(
        select(VehicleMeterReading.value)
        .where(
            VehicleMeterReading.tenant_id == tenant_id,
            VehicleMeterReading.vehicle_id == vehicle_id,
            VehicleMeterReading.meter_kind == kind,
            VehicleMeterReading.read_at <= closed_at,
        )
        .order_by(VehicleMeterReading.read_at.desc(), VehicleMeterReading.recorded_at.desc())
        .limit(1)
    ).scalar_one_or_none()
