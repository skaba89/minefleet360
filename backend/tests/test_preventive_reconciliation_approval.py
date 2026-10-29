"""Vérifier la concordance des justificatifs et des cumuls réconciliés."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.maintenance.preventive_approval_evidence import ApprovalEvidence
from app.maintenance.preventive_meter_reconciliation import (
    ReconciledMeter,
    current_meters_from_reconciliation,
)
from app.maintenance.preventive_reconciliation_approval import approved_reconciliation

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)


def _proof(reference: str = "CERT-123", *, time: datetime = NOW) -> ApprovalEvidence:
    return ApprovalEvidence(uuid.uuid4(), time, reference, False)


def _reconciliation() -> ReconciledMeter:
    return ReconciledMeter(Decimal("100"), Decimal("150"), "CERT-123", True)


def test_matching_valid_evidence_preserves_approved_total() -> None:
    approved = approved_reconciliation(_reconciliation(), _proof(), as_of=NOW)
    assert current_meters_from_reconciliation(approved, None).cumulative_km == Decimal("150")


def test_mismatched_reference_rejects_total() -> None:
    rejected = approved_reconciliation(_reconciliation(), _proof("OTHER"), as_of=NOW)
    assert current_meters_from_reconciliation(rejected, None).cumulative_km is None


def test_future_approval_rejects_total() -> None:
    rejected = approved_reconciliation(_reconciliation(), _proof(time=NOW + timedelta(days=1)), as_of=NOW)
    assert current_meters_from_reconciliation(rejected, None).cumulative_km is None


def test_unapproved_reconciliation_cannot_be_promoted() -> None:
    item = ReconciledMeter(Decimal("100"), Decimal("150"), "CERT-123", False)
    rejected = approved_reconciliation(item, _proof(), as_of=NOW)
    assert rejected.approved is False
