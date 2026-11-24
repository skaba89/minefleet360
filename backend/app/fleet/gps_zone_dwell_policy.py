"""Pure decision gate for future zone-dwell alerts; does not write or notify.

An operator must explicitly configure a threshold for a given active geofence.
Membership is assumed to have been obtained under tenant/site RLS by the caller.
The latest measured sample must still be inside the evaluated zone.
"""

from dataclasses import dataclass
from uuid import UUID

from app.fleet.gps_zone_dwell import ZoneDwellSample, zone_dwell_minutes


@dataclass(frozen=True)
class ZoneDwellDecision:
    zone_id: UUID
    measured_minutes: float
    threshold_minutes: int | None
    eligible: bool


def evaluate_zone_dwell(
    samples: list[ZoneDwellSample],
    *,
    zone_id: UUID,
    threshold_minutes: int | None,
    zone_active: bool,
    max_gap_minutes: int = 5,
) -> ZoneDwellDecision:
    """Make an evidence-only decision; missing policy/zone/membership is never an alert.

    A measured duration is not extrapolated to wall-clock "now". This function
    does not handle persistence, deduplication or notifications.
    """
    if threshold_minutes is not None and not 1 <= threshold_minutes <= 1440:
        raise ValueError("Zone dwell threshold must be between 1 and 1440 minutes")
    if max_gap_minutes < 1:
        raise ValueError("Maximum GPS gap must be positive")
    if not zone_active or threshold_minutes is None or not samples:
        return ZoneDwellDecision(zone_id, 0.0, threshold_minutes, False)
    if zone_id not in samples[-1].active_zone_ids:
        return ZoneDwellDecision(zone_id, 0.0, threshold_minutes, False)
    minutes = zone_dwell_minutes(samples, zone_id=zone_id, max_gap_minutes=max_gap_minutes)
    return ZoneDwellDecision(zone_id, minutes, threshold_minutes, minutes >= threshold_minutes)
