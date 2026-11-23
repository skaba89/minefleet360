"""Pure eligibility rules for future prolonged geofence stops.

This module deliberately does not write alerts or change ingestion. Caller must first
verify that the vehicle positions are inside the SAME active geofence; zone membership
and tenant authorization are owned by the existing PostGIS/RLS layer.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from uuid import UUID


@dataclass(frozen=True)
class DwellPoint:
    recorded_at: datetime
    latitude: float
    longitude: float
    speed_kmh: float | None


def distance_m(a: DwellPoint, b: DwellPoint) -> float:
    """Great-circle distance in metres, sufficient for a small GPS drift radius."""
    radius_m = 6_371_000.0
    lat1, lat2 = radians(a.latitude), radians(b.latitude)
    delta_lat = lat2 - lat1
    delta_lon = radians(b.longitude - a.longitude)
    hav = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 2 * radius_m * asin(min(1.0, sqrt(hav)))


def dwell_minutes(
    points: list[DwellPoint],
    *,
    max_speed_kmh: float = 3.0,
    max_drift_m: float = 40.0,
    max_gap_minutes: int = 5,
) -> float:
    """Duration of the last continuous stationary segment, measured in event time.

    Unknown speed, late/duplicate points, missing GPS intervals and movements break
    the segment. Consecutive points must all remain close to the segment's anchor;
    this avoids incorrectly counting slow but continuous driving as a stop.

    An uninterrupted one-point segment is zero minutes, not an estimated duration.
    """
    if not 0 <= max_speed_kmh <= 30 or not 0 < max_drift_m <= 1000 or max_gap_minutes < 1:
        raise ValueError("Invalid dwell policy")
    if not points:
        return 0.0
    anchor: DwellPoint | None = None
    last: DwellPoint | None = None
    for point in points:
        if point.recorded_at.tzinfo is None:
            raise ValueError("GPS timestamps must be timezone-aware")
        if last is not None and point.recorded_at <= last.recorded_at:
            # Invalid event-time order: never let this point extend the segment.
            anchor = None
            last = None
            continue
        valid_speed = point.speed_kmh is not None and 0 <= point.speed_kmh <= max_speed_kmh
        continuous = (
            anchor is not None
            and last is not None
            and point.recorded_at - last.recorded_at <= timedelta(minutes=max_gap_minutes)
            and distance_m(anchor, point) <= max_drift_m
        )
        if not valid_speed:
            anchor = None
            last = point
        elif not continuous:
            anchor = point
            last = point
        else:
            last = point
    if anchor is None or last is None:
        return 0.0
    return (last.recorded_at - anchor.recorded_at).total_seconds() / 60.0


def is_prolonged_stop(points: list[DwellPoint], *, threshold_minutes: int, max_gap_minutes: int = 5) -> bool:
    if not 1 <= threshold_minutes <= 1440:
        raise ValueError("Threshold must be between 1 and 1440 minutes")
    return dwell_minutes(points, max_gap_minutes=max_gap_minutes) >= threshold_minutes


@dataclass(frozen=True)
class ZoneDwellSample:
    """One measured GPS position with its active geofence membership from PostGIS."""

    point: DwellPoint
    active_zone_ids: frozenset[UUID]


def zone_dwell_minutes(
    samples: list[ZoneDwellSample],
    *,
    zone_id: UUID,
    max_speed_kmh: float = 3.0,
    max_drift_m: float = 40.0,
    max_gap_minutes: int = 5,
) -> float:
    """Measure only the last uninterrupted stationary segment inside one active zone.

    Membership must be computed for each position under the caller's tenant/site
    RLS scope. Leaving the zone resets dwell time even if the vehicle is stationary
    immediately outside. Re-entry starts a new segment. This is not an alert engine.
    """
    current_segment: list[DwellPoint] = []
    for sample in samples:
        if zone_id not in sample.active_zone_ids:
            current_segment.clear()
        else:
            current_segment.append(sample.point)
    return dwell_minutes(
        current_segment,
        max_speed_kmh=max_speed_kmh,
        max_drift_m=max_drift_m,
        max_gap_minutes=max_gap_minutes,
    )
