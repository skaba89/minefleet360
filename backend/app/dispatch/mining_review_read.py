"""Read historical review decisions; never infer current operational authorization."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text

from app.authz.dependencies import Authorized
from app.authz.principal import evaluate
from app.core.errors import AppError
from app.dispatch.mining_approval_policy import ReviewDecision, ReviewStage, TechnicalReview


@dataclass(frozen=True)
class HistoricalDecision:
    decision_id: UUID
    stage: ReviewStage
    decision: ReviewDecision
    actor_user_id: UUID
    reason: str
    created_at: datetime


@dataclass(frozen=True)
class ReviewHistory:
    report_id: UUID
    digest_version: str
    evidence_digest: str
    decisions: tuple[HistoricalDecision, ...]

    def technical_review(self) -> TechnicalReview | None:
        for item in self.decisions:
            if item.stage == "TECHNICAL":
                return TechnicalReview(
                    self.report_id,
                    item.actor_user_id,
                    self.digest_version,
                    self.evidence_digest,
                    item.decision,
                )
        return None


def load_review_history(
    auth: Authorized, *, site_id: UUID, revision_id: UUID, report_id: UUID
) -> ReviewHistory:
    """Return both historical decisions from one scoped database snapshot."""
    scope = evaluate(auth.principal, "dispatch.location.read")
    if auth.principal.tenant_kind != "CUSTOMER" or scope is None or not scope.covers_site(site_id):
        raise AppError("PERMISSION_DENIED")
    if auth.principal.mfa_enrollment_pending:
        raise AppError("MFA_ENROLLMENT_REQUIRED")
    rows = auth.db.execute(
        text(
            """
            SELECT r.digest_version, r.evidence_digest, d.decision_id, d.stage,
                   d.decision, d.actor_user_id, d.reason, d.created_at
            FROM mining_readiness_report r
            LEFT JOIN mining_review_decision d
              USING (tenant_id, site_id, revision_id, report_id)
            WHERE r.tenant_id = :tenant AND r.site_id = :site
              AND r.revision_id = :revision AND r.report_id = :report
            ORDER BY CASE d.stage WHEN 'TECHNICAL' THEN 0 ELSE 1 END
            LIMIT 3
            """
        ),
        {"tenant": auth.tenant_id, "site": site_id, "revision": revision_id, "report": report_id},
    ).all()
    if not rows:
        raise AppError("NOT_FOUND")
    if len(rows) > 2:
        raise AppError("CONFLICT")
    decisions = tuple(
        HistoricalDecision(
            row.decision_id, row.stage, row.decision, row.actor_user_id, row.reason, row.created_at
        )
        for row in rows
        if row.decision_id is not None
    )
    return ReviewHistory(report_id, rows[0].digest_version, rows[0].evidence_digest, decisions)
