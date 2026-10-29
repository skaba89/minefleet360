"""Journaliser la revue d'un cumul de compteur dans l'audit existant.

Cette fonction n'approuve PAS un compteur : la preuve métier durable,
l'autorisation de l'approbateur et la réconciliation seront ajoutées
dans un flux transactionnel dédié.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.audit.contracts import record
from app.maintenance.preventive_approval_evidence import ApprovalEvidence, valid_approval_evidence


def record_reconciliation_review(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    site_id: uuid.UUID,
    actor_id: uuid.UUID,
    evidence: ApprovalEvidence,
    as_of: datetime,
) -> bool:
    """Tracer la décision dans la transaction appelante, sans la valider ici."""
    accepted = evidence.approved_by == actor_id and valid_approval_evidence(evidence, as_of=as_of)
    record(
        db,
        tenant_id=tenant_id,
        site_id=site_id,
        actor_user_id=actor_id,
        action="maintenance.meter.reconciliation_review",
        entity_type="vehicle",
        entity_id=vehicle_id,
        outcome="SUCCESS" if accepted else "DENIED",
        reason=None if accepted else "INVALID_APPROVAL_EVIDENCE",
        changed_fields=("meter_reconciliation_review",),
    )
    return accepted
