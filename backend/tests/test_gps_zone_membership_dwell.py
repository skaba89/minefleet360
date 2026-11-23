"""Zone membership must reset dwell when a vehicle exits or changes zones."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.fleet.gps_zone_dwell import DwellPoint, ZoneDwellSample, zone_dwell_minutes

BASE = datetime(2026, 11, 23, 11, 0, tzinfo=UTC)


def sample(minutes: int, zones: frozenset[UUID], *, lat: float = 10.0) -> ZoneDwellSample:
    return ZoneDwellSample(
        point=DwellPoint(BASE + timedelta(minutes=minutes), lat, -12.0, 0.0),
        active_zone_ids=zones,
    )


def test_continuous_presence_inside_same_zone() -> None:
    zone = uuid4()
    events = [sample(t, frozenset({zone})) for t in (0, 3, 6, 9)]
    assert zone_dwell_minutes(events, zone_id=zone) == 9.0


def test_exiting_zone_resets_even_if_vehicle_does_not_move() -> None:
    zone = uuid4()
    events = [
        sample(0, frozenset({zone})),
        sample(3, frozenset({zone})),
        sample(6, frozenset()),
        sample(9, frozenset({zone})),
        sample(12, frozenset({zone})),
    ]
    assert zone_dwell_minutes(events, zone_id=zone) == 3.0


def test_another_zone_cannot_extend_dwell() -> None:
    zone, another = uuid4(), uuid4()
    events = [
        sample(0, frozenset({zone})),
        sample(3, frozenset({zone, another})),
        sample(6, frozenset({another})),
        sample(9, frozenset({another})),
    ]
    assert zone_dwell_minutes(events, zone_id=zone) == 0.0
    assert zone_dwell_minutes(events, zone_id=another) == 6.0


def test_missing_zone_and_gaps_do_not_estimate_presence() -> None:
    zone = uuid4()
    assert zone_dwell_minutes([sample(0, frozenset()), sample(4, frozenset())], zone_id=zone) == 0.0
    assert (
        zone_dwell_minutes([sample(0, frozenset({zone})), sample(10, frozenset({zone}))], zone_id=zone)
        == 0.0
    )


def test_movement_cancels_the_stationary_segment() -> None:
    zone = uuid4()
    assert zone_dwell_minutes(
        [sample(0, frozenset({zone})), sample(3, frozenset({zone}), lat=10.01)],
        zone_id=zone,
    ) == 0.0
