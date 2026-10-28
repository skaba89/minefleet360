from datetime import date
from decimal import Decimal

import pytest

from app.maintenance.preventive import CurrentMeters, ServiceBaseline, ServiceRule, evaluate_due


def test_calendar_due_at_boundary() -> None:
    result = evaluate_due(
        ServiceRule(days_interval=30),
        ServiceBaseline(serviced_on=date(2026, 10, 1)),
        CurrentMeters(),
        date(2026, 10, 31),
    )
    assert result.status == "DUE"
    assert result.due_triggers == ("DAYS",)


def test_km_due_before_calendar_and_hours() -> None:
    result = evaluate_due(
        ServiceRule(km_interval=Decimal("500"), hours_interval=Decimal("100"), days_interval=30),
        ServiceBaseline(date(2026, 10, 25), Decimal("1000"), Decimal("10")),
        CurrentMeters(Decimal("1500"), Decimal("50")),
        date(2026, 10, 28),
    )
    assert result.status == "DUE"
    assert result.due_triggers == ("KM",)


def test_missing_meter_does_not_mean_not_due() -> None:
    result = evaluate_due(
        ServiceRule(km_interval=Decimal("500")),
        ServiceBaseline(cumulative_km=Decimal("1000")),
        CurrentMeters(),
        date(2026, 10, 28),
    )
    assert result.status == "INSUFFICIENT_DATA"
    assert result.unknown_triggers == ("KM",)


def test_reset_not_reconciled_is_unknown() -> None:
    result = evaluate_due(
        ServiceRule(hours_interval=Decimal("50")),
        ServiceBaseline(cumulative_hours=Decimal("200")),
        CurrentMeters(cumulative_hours=Decimal("12"), hours_reliable=False),
        date(2026, 10, 28),
    )
    assert result.status == "INSUFFICIENT_DATA"


def test_calendar_due_even_if_meter_unknown() -> None:
    result = evaluate_due(
        ServiceRule(km_interval=Decimal("100"), days_interval=10),
        ServiceBaseline(serviced_on=date(2026, 10, 1)),
        CurrentMeters(),
        date(2026, 10, 28),
    )
    assert result.status == "DUE"
    assert result.due_triggers == ("DAYS",)
    assert result.unknown_triggers == ("KM",)


def test_no_thresholds() -> None:
    result = evaluate_due(ServiceRule(),
        ServiceBaseline(),
        CurrentMeters(),
        date(2026, 10, 28))
    assert result.status == "NOT_CONFIGURED"


def test_rule_validation() -> None:
    with pytest.raises(ValueError):
        ServiceRule(km_interval=Decimal("0"))
    with pytest.raises(ValueError):
        ServiceRule(hours_interval=Decimal("NaN"))
    with pytest.raises(ValueError):
        ServiceRule(days_interval=-1)
