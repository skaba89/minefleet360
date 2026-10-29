"""Le calcul préventif ne transforme jamais les relevés bruts en échéances."""

from datetime import date
from decimal import Decimal

from app.maintenance.preventive import ServiceBaseline, ServiceRule, evaluate_due
from app.maintenance.preventive_meter_adapter import current_meters_from_evidence
from app.maintenance.preventive_meter_evidence import MeterEvidence


def test_unverified_evidence_never_triggers_a_meter_due() -> None:
    km = MeterEvidence(Decimal("999999"), None, False)
    hours = MeterEvidence(Decimal("999999"), None, True)
    meters = current_meters_from_evidence(km, hours)
    result = evaluate_due(
        ServiceRule(km_interval=Decimal("100"), hours_interval=Decimal("10")),
        ServiceBaseline(cumulative_km=Decimal("100"), cumulative_hours=Decimal("10")),
        meters,
        date(2026, 10, 29),
    )
    assert result.status == "INSUFFICIENT_DATA"
    assert result.due_triggers == ()
    assert result.unknown_triggers == ("KM", "HOURS")


def test_calendar_due_still_works_with_unverified_meters() -> None:
    evidence = MeterEvidence(None, None, False)
    meters = current_meters_from_evidence(evidence, evidence)
    result = evaluate_due(
        ServiceRule(days_interval=30, km_interval=Decimal("100")),
        ServiceBaseline(serviced_on=date(2026, 1, 1)),
        meters,
        date(2026, 10, 29),
    )
    assert result.status == "DUE"
    assert result.due_triggers == ("DAYS",)
