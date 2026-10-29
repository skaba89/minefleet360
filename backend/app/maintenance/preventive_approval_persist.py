"""Persistance transactionnelle d'une approbation de cumul réconcilié."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.audit.contracts import record
from app.maintenance.preventive_approval_evidence import ApprovalEvidence
from app.maintenance.preventive_meter_reconciliation import ReconciledMeter
from app.maintenance.preventive_models import MeterReconciliationApproval
from app.maintenance.preventive_reconciliation_approval import approved_reconciliation

METER_KINDS = {"ODOMETER_KM", "HOUR_METER"}


def persist_meter_reconciliation_approval(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    site_id: uuid.UUID,
    actor_id: uuid.UUID,
    meter_kind: str,
    reconciliation: ReconciledMeter,
    evidence: ApprovalEvidence,
    as_of: datetime,
) -> bool:
    """Ajouter cumul et audit dans la transaction appelante, sans commit autonome.

    L'appelant doit avoir vérifié la permission et la portée tenant/site. Les valeurs
    ne sont persistées que si le justificatif, son auteur, sa date, sa référence et le
    cumul sont concordants.
    """
    approved = approved_reconciliation(reconciliation, evidence, as_of=as_of)
    accepted = (
        actor_id == evidence.approved_by
        and meter_kind in METER_KINDS
        and approved.approved
        and not approved.unresolved_reset
        and approved.baseline_total.is_finite()
        and approved.current_total.is_finite()
        and Decimal("0") <= approved.baseline_total <= approved.current_total
        and approved.current_total < Decimal("100000000")
        and len(approved.reconciliation_reference.strip()) <= 160
    )
    if accepted:
        assert evidence.approved_at is not None
        db.add(
            MeterReconciliationApproval(
                tenant_id=tenant_id,
                vehicle_id=vehicle_id,
                site_id=site_id,
                meter_kind=meter_kind,
                baseline_total=approved.baseline_total,
                current_total=approved.current_total,
                reconciliation_reference=approved.reconciliation_reference.strip(),
                approved_by=actor_id,
                approved_at=evidence.approved_at,
            )
        )
    record(
        db,
        tenant_id=tenant_id,
        site_id=site_id,
        actor_user_id=actor_id,
        action="maintenance.meter.reconciliation_approval",
        entity_type="vehicle",
        entity_id=vehicle_id,
        outcome="SUCCESS" if accepted else "DENIED",
        reason=None if accepted else "INVALID_RECONCILIATION_APPROVAL",
        changed_fields=("meter_reconciliation_approval",) if accepted else (),
    )
    return accepted
