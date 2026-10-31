"""Deterministic insurance expiration calculations."""

from datetime import date

import pytest

from app.legal.insurance_rules import CoverageStatus, coverage_status


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2025, 12, 31), CoverageStatus.NOT_STARTED),
        (date(2026, 1, 1), CoverageStatus.ACTIVE),
        (date(2026, 11, 30), CoverageStatus.ACTIVE),
        (date(2026, 12, 1), CoverageStatus.EXPIRING),
        (date(2026, 12, 31), CoverageStatus.EXPIRING),
        (date(2027, 1, 1), CoverageStatus.EXPIRED),
    ],
)
def test_coverage_lifecycle(today: date, expected: CoverageStatus) -> None:
    assert coverage_status(date(2026, 1, 1), date(2026, 12, 31), today) == expected


def test_zero_day_warning_is_expiring_only_on_last_day() -> None:
    assert (
        coverage_status(date(2026, 1, 1), date(2026, 12, 31), date(2026, 12, 30), 0) == CoverageStatus.ACTIVE
    )
    assert (
        coverage_status(date(2026, 1, 1), date(2026, 12, 31), date(2026, 12, 31), 0)
        == CoverageStatus.EXPIRING
    )


@pytest.mark.parametrize(
    ("start", "end", "warning_days"),
    [
        (date(2026, 12, 31), date(2026, 1, 1), 30),
        (date(2026, 1, 1), date(2026, 12, 31), -1),
    ],
)
def test_invalid_coverage_inputs(start: date, end: date, warning_days: int) -> None:
    with pytest.raises(ValueError):
        coverage_status(start, end, date(2026, 10, 31), warning_days)
