"""Pure dwell calculations: no database, network, or alert side effects."""

from datetime import UTC, datetime, timedelta

import pytest

from app.fleet.gps_zone_dwell import DwellPoint, dwell_minutes, is_prolonged_stop


BASE = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)


def point(minutes: int, *, lat: float = 10.0, lon: float = -12.0, speed: float | None = 0.0) -> DwellPoint:
    return DwellPoint(BASE + timedelta(minutes=minutes), lat, lon, speed)


def test_stationary_measured_positions_reach_threshold_exactly() -> None:
    positions = [point(t) for t in (0, 4, 8, 12, 16)]
    assert dwell_minutes(positions) == 16
    assert is_prolonged_stop(positions, threshold_minutes=15)
    assert not is_prolonged_stop(positions, threshold_minutes=17)


def test_no_extrapolation_without_measured_positions() -> None:
    assert dwell_minutes([]) == 0
    assert dwell_minutes([point(0)]) == 0
    assert not is_prolonged_stop([point(0)], threshold_minutes=1)


@pytest.mark.parametrize(
    "positions",
    [
        [point(0), point(3), point(15)],  # missing reception interval
        [point(0), point(3, speed=None), point(6)],  # absent speed evidence
        [point(0), point(3, speed=12), point(6)],  # driving
        [point(0), point(3, lon=-11.998), point(6)],  # position jump
        [point(0), point(3), point(2), point(6)],  # out-of-order position
    ],
)
def test_uncertain_or_moving_data_cannot_trigger_false_stop(positions: list[DwellPoint]) -> None:
    assert not is_prolonged_stop(positions, threshold_minutes=5)


def test_small_position_drift_is_tolerated() -> None:
    assert dwell_minutes([point(0), point(4, lat=10.00005), point(8, lat=10.00008)]) == 8


def test_rejects_naive_timestamps_and_unreasonable_policies() -> None:
    with pytest.raises(ValueError):
        dwell_minutes([DwellPoint(datetime(2026, 11, 23), 10, -12, 0)])
    with pytest.raises(ValueError):
        is_prolonged_stop([point(0)], threshold_minutes=0)
    with pytest.raises(ValueError):
        is_prolonged_stop([point(0)], threshold_minutes=1441)
