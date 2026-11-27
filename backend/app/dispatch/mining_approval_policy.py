"""Pure prerequisite checks for proposed review decisions, not authorization.

The caller must separately authorize reviewers, qualify the survey tolerance,
load trusted evidence, serialize concurrent changes and persist an audit trail.
"""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.dispatch.mining_readiness_snapshot import DraftReadinessEvidence
from app.dispatch.mining_report_read import HistoricalReport

ReviewStage = Literal["TECHNICAL", "HSE"]
ReviewDecision = Literal["APPROVED", "REJECTED"]


@dataclass(frozen=True)
class TechnicalReview:
    report_id: UUID
    actor_user_id: UUID
    digest_version: str
    evidence_digest: str
    decision: ReviewDecision


def review_blockers(
    report: HistoricalReport,
    current: DraftReadinessEvidence,
    *,
    stage: ReviewStage,
    reviewer_id: UUID,
    technical_review: TechnicalReview | None = None,
) -> tuple[str, ...]:
    """Check identity, integrity and separation of duties; never write a decision."""
    blockers: list[str] = []
    summary = report.summary
    if summary.finding_count != len(report.findings):
        blockers.append("INCONSISTENT_REPORT")
    if report.findings or current.findings:
        blockers.append("TECHNICAL_FINDINGS")
    if (summary.digest_version, summary.evidence_digest) != (current.digest_version, current.digest):
        blockers.append("STALE_EVIDENCE")
    if reviewer_id == summary.actor_user_id:
        blockers.append("SELF_REVIEW")
    if stage == "TECHNICAL":
        if technical_review is not None:
            blockers.append("UNEXPECTED_PRIOR_REVIEW")
    elif stage == "HSE":
        if technical_review is None:
            blockers.append("TECHNICAL_REVIEW_REQUIRED")
        else:
            if (
                technical_review.report_id != summary.report_id
                or technical_review.digest_version != summary.digest_version
                or technical_review.evidence_digest != summary.evidence_digest
                or technical_review.decision != "APPROVED"
            ):
                blockers.append("INVALID_TECHNICAL_REVIEW")
            if (
                technical_review.actor_user_id == reviewer_id
                or technical_review.actor_user_id == summary.actor_user_id
            ):
                blockers.append("REVIEWER_NOT_INDEPENDENT")
    else:
        blockers.append("UNKNOWN_REVIEW_STAGE")
    return tuple(blockers)
