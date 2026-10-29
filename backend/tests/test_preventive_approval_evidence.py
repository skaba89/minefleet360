"""Validation déterministe des justificatifs d'approbation."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.maintenance.preventive_approval_evidence import ApprovalEvidence, valid_approval_evidence

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)


def _evidence() -> ApprovalEvidence:
    return ApprovalEvidence(
        approved_by=uuid.uuid4(),
        approved_at=NOW,
        reference="RECON-2026-001",
        unresolved_reset=False,
    )


def test_complete_evidence_is_accepted() -> None:
    assert valid_approval_evidence(_evidence(), as_of=NOW)


@pytest.mark.parametrize("case", ["missing_actor", "missing_date", "future", "blank_reference", "reset"])
def test_incomplete_approval_is_rejected(case: str) -> None:
    evidence = _evidence()
    if case == "missing_actor":
        evidence = ApprovalEvidence(None, evidence.approved_at, evidence.reference, False)
    elif case == "missing_date":
        evidence = ApprovalEvidence(evidence.approved_by, None, evidence.reference, False)
    elif case == "future":
        evidence = ApprovalEvidence(evidence.approved_by, NOW + timedelta(days=1), evidence.reference, False)
    elif case == "blank_reference":
        evidence = ApprovalEvidence(evidence.approved_by, evidence.approved_at, " ", False)
    else:
        evidence = ApprovalEvidence(evidence.approved_by, evidence.approved_at, evidence.reference, True)
    assert not valid_approval_evidence(evidence, as_of=NOW)
