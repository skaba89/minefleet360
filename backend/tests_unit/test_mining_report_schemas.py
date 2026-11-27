"""Contracts must not accept client-supplied evidence or imply authorization."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.dispatch.mining_readiness import ReadinessFinding
from app.dispatch.mining_report_read import HistoricalReport, ReportSummary
from app.dispatch.mining_report_schemas import (
    ReadinessReportCreate,
    ReadinessReportDetailOut,
    ReadinessReportPageOut,
)


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan"), "2", True, None])
def test_invalid_tolerance(value: object) -> None:
    with pytest.raises(ValidationError):
        ReadinessReportCreate.model_validate({"tolerance_m": value})


def test_create_contract_rejects_client_evidence() -> None:
    assert ReadinessReportCreate(tolerance_m=2).tolerance_m == 2
    for field in ("tenant_id", "actor_user_id", "evidence_digest", "findings", "approved", "status"):
        with pytest.raises(ValidationError):
            ReadinessReportCreate.model_validate({"tolerance_m": 2, field: "forged"})


def test_historical_report_contract() -> None:
    summary = ReportSummary(
        UUID(int=1), "mining-readiness-v1", "a" * 64, 2.0, UUID(int=2), datetime(2026, 11, 27, tzinfo=UTC), 1
    )
    detail = ReadinessReportDetailOut.from_report(
        HistoricalReport(summary, (ReadinessFinding("MISSING_RESTRICTION", UUID(int=3)),))
    )
    result = detail.model_dump(mode="json")
    assert result["summary"]["evidence_kind"] == "HISTORICAL_TECHNICAL_INSPECTION"
    assert result["findings"] == [{"code": "MISSING_RESTRICTION", "segment_id": str(UUID(int=3))}]
    assert "approved" not in result["summary"]
    page = ReadinessReportPageOut.from_page([summary], summary.report_id)
    assert page.items == [detail.summary]
    assert page.next_cursor == summary.report_id
    assert ReadinessReportPageOut.from_page([], None).model_dump() == {"items": [], "next_cursor": None}
