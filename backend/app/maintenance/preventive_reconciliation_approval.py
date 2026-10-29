"""Lier une approbation datée à un cumul réconcilié.

Pure validation: la preuve est fournie par l'appelant; son authenticité, RBAC,
RLS et la conservation en base doivent être vérifiés par un service distinct.
"""

from datetime import datetime

from app.maintenance.preventive_approval_evidence import ApprovalEvidence, valid_approval_evidence
from app.maintenance.preventive_meter_reconciliation import ReconciledMeter


def approved_reconciliation(
    reconciliation: ReconciledMeter, evidence: ApprovalEvidence, *, as_of: datetime
) -> ReconciledMeter:
    """Ne jamais accepter le booléen approved sans justificatif concordant."""
    valid = (
        reconciliation.approved
        and not reconciliation.unresolved_reset
        and valid_approval_evidence(evidence, as_of=as_of)
        and reconciliation.reconciliation_reference.strip() == evidence.reference.strip()
    )
    return ReconciledMeter(
        baseline_total=reconciliation.baseline_total,
        current_total=reconciliation.current_total,
        reconciliation_reference=reconciliation.reconciliation_reference,
        approved=valid,
        unresolved_reset=reconciliation.unresolved_reset or evidence.unresolved_reset,
    )
