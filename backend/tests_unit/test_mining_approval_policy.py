"""Pure checks do not grant permissions or activate a network."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from app.dispatch.mining_approval_policy import TechnicalReview, review_blockers
from app.dispatch.mining_readiness import ReadinessFinding
from app.dispatch.mining_readiness_snapshot import DraftReadinessEvidence
from app.dispatch.mining_report_read import HistoricalReport, ReportSummary

REPORT, AUTHOR, TECH, HSE, OTHER = (UUID(int=i) for i in range(1, 6))
EVIDENCE = DraftReadinessEvidence("mining-readiness-v1", "a" * 64, ())
SUMMARY = ReportSummary(
    REPORT, EVIDENCE.digest_version, EVIDENCE.digest, 2.0, AUTHOR, datetime(2026, 11, 27, tzinfo=UTC), 0
)
HISTORY = HistoricalReport(SUMMARY, ())
TECHNICAL = TechnicalReview(REPORT, TECH, EVIDENCE.digest_version, EVIDENCE.digest, "APPROVED")


def test_independent_reviews() -> None:
    assert review_blockers(HISTORY, EVIDENCE, stage="TECHNICAL", reviewer_id=TECH) == ()
    assert review_blockers(HISTORY, EVIDENCE, stage="HSE", reviewer_id=HSE, technical_review=TECHNICAL) == ()


def test_stale_and_failed_evidence() -> None:
    stale = replace(EVIDENCE, digest="b" * 64)
    assert review_blockers(HISTORY, stale, stage="TECHNICAL", reviewer_id=TECH) == ("STALE_EVIDENCE",)
    finding = ReadinessFinding("EMPTY_GRAPH")
    failed = replace(EVIDENCE, findings=(finding,))
    assert review_blockers(HISTORY, failed, stage="TECHNICAL", reviewer_id=TECH) == ("TECHNICAL_FINDINGS",)
    inconsistent = replace(HISTORY, findings=(finding,))
    assert review_blockers(inconsistent, EVIDENCE, stage="TECHNICAL", reviewer_id=TECH) == (
        "INCONSISTENT_REPORT",
        "TECHNICAL_FINDINGS",
    )


def test_separation_of_duties() -> None:
    assert review_blockers(HISTORY, EVIDENCE, stage="TECHNICAL", reviewer_id=AUTHOR) == ("SELF_REVIEW",)
    assert review_blockers(HISTORY, EVIDENCE, stage="HSE", reviewer_id=HSE) == ("TECHNICAL_REVIEW_REQUIRED",)
    assert review_blockers(HISTORY, EVIDENCE, stage="HSE", reviewer_id=TECH, technical_review=TECHNICAL) == (
        "REVIEWER_NOT_INDEPENDENT",
    )
    same_author = replace(TECHNICAL, actor_user_id=AUTHOR)
    assert review_blockers(HISTORY, EVIDENCE, stage="HSE", reviewer_id=HSE, technical_review=same_author) == (
        "REVIEWER_NOT_INDEPENDENT",
    )


def test_hse_requires_matching_positive_technical_review() -> None:
    for review in (
        replace(TECHNICAL, report_id=OTHER),
        replace(TECHNICAL, digest_version="unknown"),
        replace(TECHNICAL, evidence_digest="b" * 64),
        replace(TECHNICAL, decision="REJECTED"),
    ):
        assert review_blockers(HISTORY, EVIDENCE, stage="HSE", reviewer_id=HSE, technical_review=review) == (
            "INVALID_TECHNICAL_REVIEW",
        )
