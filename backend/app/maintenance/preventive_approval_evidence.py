"""Validation pure des justificatifs d'approbation de compteurs.

Cette étape ne remplace pas les droits RBAC, l'audit ni la persistance.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class ApprovalEvidence:
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    reference: str
    unresolved_reset: bool


def valid_approval_evidence(evidence: ApprovalEvidence, *, as_of: datetime) -> bool:
    """Refuser une approbation incomplète, future ou non traçable."""
    if evidence.approved_by is None or evidence.approved_by.int == 0:
        return False
    if evidence.unresolved_reset or not evidence.reference.strip():
        return False
    approved_at = evidence.approved_at
    if approved_at is None or approved_at.tzinfo is None or as_of.tzinfo is None:
        return False
    return approved_at.astimezone(UTC) <= as_of.astimezone(UTC)
