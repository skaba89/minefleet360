"""Les clés ne dépendent ni de la date du job ni de sa répétition."""

from datetime import date
from decimal import Decimal

from app.maintenance.preventive import CurrentMeters, ServiceBaseline, ServiceRule
from app.maintenance.preventive_due_candidates import due_candidates


def test_calendar_candidate_is_stable_when_job_runs_again() -> None:
    rule = ServiceRule(days_interval=30)
    baseline = ServiceBaseline(serviced_on=date(2026, 1, 1))
    first = due_candidates(rule, baseline, CurrentMeters(), date(2026, 2, 1))
    replay = due_candidates(rule, baseline, CurrentMeters(), date(2026, 3, 1))
    assert first == replay
    assert first[0].due_on == date(2026, 1, 31)


def test_km_candidate_is_stable_after_extra_driving() -> None:
    rule = ServiceRule(km_interval=Decimal("500"))
    baseline = ServiceBaseline(cumulative_km=Decimal("1000"))
    one = due_candidates(rule, baseline, CurrentMeters(cumulative_km=Decimal("1501")), date(2026, 10, 28))
    two = due_candidates(rule, baseline, CurrentMeters(cumulative_km=Decimal("2000")), date(2026, 10, 29))
    assert one == two
    assert one[0].trigger_kind == "KM"
    assert one[0].due_meter == Decimal("1500")


def test_two_thresholds_create_one_candidate() -> None:
    rule = ServiceRule(km_interval=Decimal("500"), days_interval=30)
    baseline = ServiceBaseline(serviced_on=date(2026, 1, 1), cumulative_km=Decimal("1000"))
    candidates = due_candidates(
        rule, baseline, CurrentMeters(cumulative_km=Decimal("1800")), date(2026, 2, 15)
    )
    assert len(candidates) == 1
    assert candidates[0].trigger_kind == "DAYS"


def test_missing_meters_produce_no_false_due() -> None:
    rule = ServiceRule(hours_interval=Decimal("100"))
    assert due_candidates(rule, ServiceBaseline(), CurrentMeters(), date(2026, 10, 28)) == ()


def test_reset_without_reconciliation_produces_no_candidate() -> None:
    rule = ServiceRule(km_interval=Decimal("500"))
    baseline = ServiceBaseline(cumulative_km=Decimal("1000"))
    meters = CurrentMeters(cumulative_km=Decimal("100"), km_reliable=False)
    assert due_candidates(rule, baseline, meters, date(2026, 10, 28)) == ()
