"""Validate route evidence before using it for advisory dispatch ranking.

A route provider must supply the distance and duration. Never derive an ETA from
instantaneous GPS speed or straight-line distance.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID


@dataclass(frozen=True)
class RouteEstimate:
    tenant_id: UUID
    site_id: UUID
    vehicle_id: UUID
    destination_id: UUID
    position_recorded_at: datetime
    position_received_at: datetime
    calculated_at: datetime
    distance_m: int
    duration_seconds: int


def usable_eta(
    estimate: RouteEstimate,
    *,
    tenant_id: UUID,
    site_id: UUID,
    vehicle_id: UUID,
    destination_id: UUID,
    now: datetime,
    max_age: timedelta = timedelta(minutes=2),
) -> int | None:
    """Reject mismatched, stale, future or inconsistent evidence; never return a fabricated ETA."""
    if (
        estimate.tenant_id != tenant_id
        or estimate.site_id != site_id
        or estimate.vehicle_id != vehicle_id
        or estimate.destination_id != destination_id
        or max_age <= timedelta(0)
    ):
        return None
    times = (estimate.position_recorded_at, estimate.position_received_at, estimate.calculated_at, now)
    if any(value.tzinfo is None or value.utcoffset() is None for value in times):
        return None
    recorded, received, calculated, current = times
    if not current - max_age <= recorded <= received <= calculated <= current:
        return None
    if estimate.distance_m < 0 or estimate.duration_seconds < 0:
        return None
    if estimate.distance_m > 0 and estimate.duration_seconds == 0:
        return None
    return estimate.duration_seconds
