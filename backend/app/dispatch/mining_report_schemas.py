"""Strict API contracts for historical technical reports, not approvals."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.http import StrictModel
from app.dispatch.mining_report_read import HistoricalReport, ReportSummary


class ReadinessReportCreate(StrictModel):
    """The tolerance must be justified by the survey; the server computes all evidence."""

    tolerance_m: float = Field(ge=0, allow_inf_nan=False, strict=True)


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
