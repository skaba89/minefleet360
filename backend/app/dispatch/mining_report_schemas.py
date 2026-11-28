"""Strict API contracts for historical technical reports and review decisions."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.http import StrictModel
from app.dispatch.mining_report_read import HistoricalReport, ReportSummary
from app.dispatch.mining_review_read import HistoricalDecision, ReviewHistory


class ReadinessReportCreate(StrictModel):
    """The tolerance must be justified by an approved survey qualification; the server computes evidence."""

    tolerance_m: float = Field(ge=0, allow_inf_nan=False, strict=True)
    tolerance_qualification_id: UUID


class ReadinessReviewCreate(StrictModel):
    """A motivated historical decision; the service re-validates stage, role and evidence."""

    stage: Literal["TECHNICAL", "HSE"]
    reason: str = Field(min_length=1, max_length=500)


class ReadinessFindingOut(BaseModel):
    code: str
    segment_id: UUID | None


class ReadinessReportSummaryOut(BaseModel):
    report_id: UUID
    digest_version: str
    evidence_digest: str
    tolerance_m: float
    actor_user_id: UUID
    created_at: datetime
    finding_count: int
    tolerance_qualification_id: UUID | None = None
    evidence_kind: Literal["HISTORICAL_TECHNICAL_INSPECTION"] = "HISTORICAL_TECHNICAL_INSPECTION"

    @classmethod
    def from_summary(cls, summary: ReportSummary) -> "ReadinessReportSummaryOut":
        return cls(
            report_id=summary.report_id,
            digest_version=summary.digest_version,
            evidence_digest=summary.evidence_digest,
            tolerance_m=summary.tolerance_m,
            actor_user_id=summary.actor_user_id,
            created_at=summary.created_at,
            finding_count=summary.finding_count,
            tolerance_qualification_id=summary.tolerance_qualification_id,
        )


class ReadinessReportDetailOut(BaseModel):
    summary: ReadinessReportSummaryOut
    findings: list[ReadinessFindingOut]

    @classmethod
    def from_report(cls, report: HistoricalReport) -> "ReadinessReportDetailOut":
        return cls(
            summary=ReadinessReportSummaryOut.from_summary(report.summary),
            findings=[
                ReadinessFindingOut(code=item.code, segment_id=item.segment_id) for item in report.findings
            ],
        )


class ReadinessReportPageOut(BaseModel):
    items: list[ReadinessReportSummaryOut]
    next_cursor: UUID | None

    @classmethod
    def from_page(cls, summaries: list[ReportSummary], next_cursor: UUID | None) -> "ReadinessReportPageOut":
        return cls(
            items=[ReadinessReportSummaryOut.from_summary(item) for item in summaries],
            next_cursor=next_cursor,
        )


class ReadinessDecisionOut(BaseModel):
    decision_id: UUID
    report_id: UUID
    stage: Literal["TECHNICAL", "HSE"]
    decision: Literal["APPROVED", "REJECTED"]
    actor_user_id: UUID
    reason: str
    created_at: datetime
    evidence_kind: Literal["MINING_REVIEW_DECISION"] = "MINING_REVIEW_DECISION"

    @classmethod
    def from_decision(cls, report_id: UUID, item: HistoricalDecision) -> "ReadinessDecisionOut":
        return cls(
            decision_id=item.decision_id,
            report_id=report_id,
            stage=item.stage,
            decision=item.decision,
            actor_user_id=item.actor_user_id,
            reason=item.reason,
            created_at=item.created_at,
        )


class ReadinessReviewHistoryOut(BaseModel):
    report_id: UUID
    digest_version: str
    evidence_digest: str
    decisions: list[ReadinessDecisionOut]
    evidence_kind: Literal["MINING_REVIEW_HISTORY"] = "MINING_REVIEW_HISTORY"

    @classmethod
    def from_history(cls, history: ReviewHistory) -> "ReadinessReviewHistoryOut":
        return cls(
            report_id=history.report_id,
            digest_version=history.digest_version,
            evidence_digest=history.evidence_digest,
            decisions=[
                ReadinessDecisionOut.from_decision(history.report_id, item) for item in history.decisions
            ],
        )
