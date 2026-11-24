"""No dwell alert may be eligible without an explicit active-zone policy."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.fleet.gps_zone_dwell import DwellPoint, ZoneDwellSample
from app.fleet.gps_zone_dwell_policy import evaluate_zone_dwell

BASE = datetime(2026, 11, 24, 7, 0, tzinfo=UTC)


def sample(minutes: int, zones: frozenset[UUID], *, lat: float = 10.0, speed: float | None = 0.0) -> ZoneDwellSample:
    return ZoneDwellSample(
        point=DwellPoint(BASE + timedelta(minutes=minutes), lat, -12.0, speed),
        active_zone_ids=zones,
    )


def test_threshold_is_explicit_and_reached_only_with_measured_evidence() -> None:
    zone = uuid4()
    points = [sample(t, frozenset({zone})) for t in (0, 3, 6, 9)]
    eligible = evaluate_zone_dwell(points, zone_id=zone, threshold_minutes=9, zone_active=True)
    assert eligible.eligible
    assert eligible.measured_minutes == 9.0
    assert not evaluate_zone_dwell(points, zone_id=zone, threshold_minutes=10, zone_active=True).eligible


def test_no_policy_or_inactive_geofence_never_triggers() -> None:
    zone = uuid4()
    points = [sample(t, frozenset({zone})) for t in (0, 3, 6, 9)]
    assert not evaluate_zone_dwell(points, zone_id=zone, threshold_minutes=None, zone_active=True).eligible
    assert not evaluate_zone_dwell(points, zone_id=zone, threshold_minutes=5, zone_active=False).eligible


def test_last_sample_outside_zone_never_triggers_after_exit() -> None:
    zone = uuid4()
    points = [sample(t, frozenset({zone})) for t in (0, 3, 6, 9)]
    points.append(sample(12, frozenset()))
    result = evaluate_zone_dwell(points, zone_id=zone, threshold_minutes=5, zone_active=True)
    assert not result.eligible
    assert result.measured_minutes == 0.0


def test_zone_reentry_starts_new_interval() -> None:
    zone = uuid4()
    points = [
        sample(0, frozenset({zone})),
        sample(3, frozenset({zone})),
        sample(6, frozenset()),
        sample(9, frozenset({zone})),
        sample(12, frozenset({zone})),
    ]
    result = evaluate_zone_dwell(points, zone_id=zone, threshold_minutes=5, zone_active=True)
    assert result.measured_minutes == 3.0
    assert not result.eligible


def test_moving_unknown_speed_and_missing_measurements_do_not_estimate_stops() -> None:
    zone = uuid4()
    points = [
        sample(0, frozenset({zone})),
        sample(3, frozenset({zone}), speed=10),
        sample(6, frozenset({zone}), speed=None),
        sample(9, frozenset({zone})),
    ]
    assert not evaluate_zone_dwell(points, zone_id=zone, threshold_minutes=1, zone_active=True).eligible
    gap = [sample(0, frozenset({zone})), sample(9, frozenset({zone}))]
    assert not evaluate_zone_dwell(gap, zone_id=zone, threshold_minutes=1, zone_active=True).eligible


def test_each_overlapping_zone_is_evaluated_independently() -> None:
    a, b = uuid4(), uuid4()
    points = [
        sample(0, frozenset({a})),
        sample(3, frozenset({a, b})),
        sample(6, frozenset({a, b})),
        sample(9, frozenset({a, b})),
    ]
    assert evaluate_zone_dwell(points, zone_id=a, threshold_minutes=9, zone_active=True).eligible
    assert not evaluate_zone_dwell(points, zone_id=b, threshold_minutes=9, zone_active=True).eligible


@pytest.mark.parametrize("threshold", [0, -1, 1441])
def test_invalid_threshold_is_rejected(threshold: int) -> None:
    with pytest.raises(ValueError):
        evaluate_zone_dwell([], zone_id=uuid4(), threshold_minutes=threshold, zone_active=True)


def test_missing_samples_cannot_generate_a_stop() -> None:
    zone = uuid4()
    assert not evaluate_zone_dwell([], zone_id=zone, threshold_minutes=1, zone_active=True).eligible
