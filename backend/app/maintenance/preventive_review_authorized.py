"""Point d'entrée interne autorisé pour la revue des compteurs."""

import uuid
from datetime import datetime

from sqlalchemy import select

from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.fleet.models import Vehicle
from app.maintenance.preventive_approval_evidence import ApprovalEvidence
from app.maintenance.preventive_reconciliation_review import record_reconciliation_review

REVIEW_PERMISSION = "maintenance.preventive.manage"


def review_meter_evidence(
    auth: Authorized, vehicle_id: uuid.UUID, evidence: ApprovalEvidence, *, as_of: datetime
) -> bool:
    """Exiger la permission et la portée véhicule avant toute journalisation."""
    if auth.scope.permission != REVIEW_PERMISSION:
        raise AppError("PERMISSION_DENIED")
    vehicle = auth.db.execute(
        select(Vehicle).where(Vehicle.tenant_id == auth.tenant_id, Vehicle.vehicle_id == vehicle_id)
    ).scalar_one_or_none()
    if vehicle is None or not auth.scope.covers_site(vehicle.site_id):
        raise AppError("NOT_FOUND")
    return record_reconciliation_review(
        auth.db,
        tenant_id=auth.tenant_id,
        vehicle_id=vehicle_id,
        site_id=vehicle.site_id,
        actor_id=auth.user_id,
        evidence=evidence,
        as_of=as_of,
    )


from app.maintenance.preventive_approval_persist import persist_meter_reconciliation_approval
from app.maintenance.preventive_meter_reconciliation import ReconciledMeter


def approve_meter_reconciliation(
    auth: Authorized,
    vehicle_id: uuid.UUID,
    meter_kind: str,
    reconciliation: ReconciledMeter,
    evidence: ApprovalEvidence,
    *,
    as_of: datetime,
) -> bool:
    """Persister une approbation après contrôle RBAC, tenant et site."""
    if auth.scope.permission != REVIEW_PERMISSION:
        raise AppError("PERMISSION_DENIED")
    vehicle = auth.db.execute(
        select(Vehicle).where(Vehicle.tenant_id == auth.tenant_id, Vehicle.vehicle_id == vehicle_id)
    ).scalar_one_or_none()
    if vehicle is None or not auth.scope.covers_site(vehicle.site_id):
        raise AppError("NOT_FOUND")
    return persist_meter_reconciliation_approval(
        auth.db,
        tenant_id=auth.tenant_id,
        vehicle_id=vehicle_id,
        site_id=vehicle.site_id,
        actor_id=auth.user_id,
        meter_kind=meter_kind,
        reconciliation=reconciliation,
        evidence=evidence,
        as_of=as_of,
    )
