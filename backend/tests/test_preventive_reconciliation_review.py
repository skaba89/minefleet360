"""La revue de compteur est journalisée sans approuver de cumul."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from app.maintenance.preventive_approval_evidence import ApprovalEvidence
from app.maintenance.preventive_reconciliation_review import record_reconciliation_review


NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)


def test_valid_review_is_audited_without_committing() -> None:
    db = MagicMock()
    actor = uuid.uuid4()
    evidence = ApprovalEvidence(actor, NOW, "REV-123", False)
    with patch("app.maintenance.preventive_reconciliation_review.record") as audit:
        result = record_reconciliation_review(
            db,
            tenant_id=uuid.uuid4(),
            vehicle_id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            actor_id=actor,
            evidence=evidence,
            as_of=NOW,
        )
    assert result is True
    assert audit.call_args.kwargs["outcome"] == "SUCCESS"
    db.commit.assert_not_called()


def test_different_actor_is_rejected_and_audited() -> None:
    db = MagicMock()
    evidence = ApprovalEvidence(uuid.uuid4(), NOW, "REV-123", False)
    with patch("app.maintenance.preventive_reconciliation_review.record") as audit:
        result = record_reconciliation_review(
            db,
            tenant_id=uuid.uuid4(),
            vehicle_id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            evidence=evidence,
            as_of=NOW,
        )
    assert result is False
    assert audit.call_args.kwargs["outcome"] == "DENIED"
    db.commit.assert_not_called()
