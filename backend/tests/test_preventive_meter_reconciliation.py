"""Tests du contrat de réconciliation des cumuls de compteurs."""

from decimal import Decimal

import pytest

from app.maintenance.preventive_meter_reconciliation import (
    ReconciledMeter,
    current_meters_from_reconciliation,
)


def _proof(**overrides: object) -> ReconciledMeter:
    values = {
        "baseline_total": Decimal("100.0"),
        "current_total": Decimal("125.0"),
        "reconciliation_reference": "SIGNED-REPORT-123",
        "approved": True,
        "unresolved_reset": False,
    }
    values.update(overrides)
    return ReconciledMeter(**values)  # type: ignore[arg-type]


def test_verified_totals_are_passed_independently() -> None:
    result = current_meters_from_reconciliation(_proof(), None)
    assert result.cumulative_km == Decimal("125.0")
    assert result.km_reliable is True
    assert result.cumulative_hours is None
    assert result.hours_reliable is False


@pytest.mark.parametrize(
    "changes",
    [
        {"approved": False},
        {"unresolved_reset": True},
        {"reconciliation_reference": " "},
        {"current_total": Decimal("90.0")},
        {"baseline_total": Decimal("-1.0")},
        {"current_total": Decimal("NaN")},
        {"current_total": Decimal("Infinity")},
    ],
)
def test_unreconciled_totals_are_not_trusted(changes: dict[str, object]) -> None:
    result = current_meters_from_reconciliation(_proof(**changes), None)
    assert result.cumulative_km is None
    assert result.km_reliable is False
