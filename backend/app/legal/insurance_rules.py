"""Pure insurance coverage and renewal reminder rules.

These functions do not alter policy state or send notifications. Dates are
evaluated against a caller-supplied business date for deterministic behavior.
"""

from datetime import date
from enum import StrEnum


class CoverageStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    ACTIVE = "ACTIVE"
    EXPIRING = "EXPIRING"
    EXPIRED = "EXPIRED"


def coverage_status(
    start: date, end: date, as_of: date, warning_days: int = 30
) -> CoverageStatus:
    """Classify coverage; policy end date is inclusive."""
    if end < start:
        raise ValueError("coverage_end must not precede coverage_start")
    if warning_days < 0:
        raise ValueError("warning_days must be non-negative")
    if as_of < start:
        return CoverageStatus.NOT_STARTED
    if as_of > end:
        return CoverageStatus.EXPIRED
    if (end - as_of).days <= warning_days:
        return CoverageStatus.EXPIRING
    return CoverageStatus.ACTIVE
