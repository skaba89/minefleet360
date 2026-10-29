"""Lecture conservative des cumuls approuvés pour la maintenance préventive.

Cette couche ne calcule ni ne persiste d'échéances. Une approbation est ignorée
dès qu'un relevé brut postérieur existe pour le même compteur.
"""

from datetime import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fleet.models import Vehicle, VehicleMeterReading
from app.maintenance.preventive import CurrentMeters
from app.maintenance.preventive_meter_reconciliation import (
    ReconciledMeter,
    current_meters_from_reconciliation,
)
from app.maintenance.preventive_models import MeterReconciliationApproval

_METER_KINDS = frozenset({"ODOMETER_KM", "HOUR_METER"})


def _has_reading_after_approval(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    meter_kind: str,
    approved_at: datetime,
    as_of: datetime,
) -> bool:
    statement = (
        select(VehicleMeterReading.vehicle_meter_reading_id)
        .where(
            VehicleMeterReading.tenant_id == tenant_id,
            VehicleMeterReading.vehicle_id == vehicle_id,
            VehicleMeterReading.meter_kind == meter_kind,
            VehicleMeterReading.read_at > approved_at,
            VehicleMeterReading.read_at <= as_of,
        )
        .limit(1)
    )
    return db.scalar(statement) is not None


def load_approved_current_meters(
    db: Session,
    tenant_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    site_id: uuid.UUID,
    *,
    as_of: datetime,
) -> CurrentMeters:
    """Retourne uniquement les cumuls approuvés valides à la date demandée.

    La dernière approbation de chaque type fait autorité. Si elle est périmée,
    une approbation plus ancienne ne peut pas la remplacer. Les filtres tenant,
    véhicule et site courant sont explicites en complément des politiques RLS.
    """
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        return CurrentMeters(
            cumulative_km=None,
            cumulative_hours=None,
            km_reliable=False,
            hours_reliable=False,
        )

    statement = (
        select(MeterReconciliationApproval)
        .join(
            Vehicle,
            (Vehicle.vehicle_id == MeterReconciliationApproval.vehicle_id)
            & (Vehicle.tenant_id == MeterReconciliationApproval.tenant_id),
        )
        .where(
            MeterReconciliationApproval.tenant_id == tenant_id,
            MeterReconciliationApproval.vehicle_id == vehicle_id,
            MeterReconciliationApproval.site_id == site_id,
            MeterReconciliationApproval.approved_at <= as_of,
            Vehicle.tenant_id == tenant_id,
            Vehicle.vehicle_id == vehicle_id,
            Vehicle.site_id == site_id,
        )
        .order_by(
            MeterReconciliationApproval.approved_at.desc(),
            MeterReconciliationApproval.created_at.desc(),
            MeterReconciliationApproval.approval_id.desc(),
        )
    )

    seen_kinds: set[str] = set()
    approved: dict[str, ReconciledMeter] = {}
    for approval in db.scalars(statement):
        kind = approval.meter_kind
        if kind not in _METER_KINDS or kind in seen_kinds:
            continue

        # Mark the newest record first, even if stale, so an older approval
        # cannot silently restore a value invalidated by a later raw reading.
        seen_kinds.add(kind)
        if _has_reading_after_approval(
            db,
            tenant_id=tenant_id,
            vehicle_id=vehicle_id,
            meter_kind=kind,
            approved_at=approval.approved_at,
            as_of=as_of,
        ):
            continue

        approved[kind] = ReconciledMeter(
            baseline_total=approval.baseline_total,
            current_total=approval.current_total,
            reconciliation_reference=approval.reconciliation_reference,
            approved=True,
            unresolved_reset=False,
        )

    return current_meters_from_reconciliation(
        approved.get("ODOMETER_KM"),
        approved.get("HOUR_METER"),
    )
