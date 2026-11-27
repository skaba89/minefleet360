"""Conservative closure filtering for a trusted, single-revision graph snapshot."""

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from app.dispatch.mining_routes import RoadSegment


@dataclass(frozen=True)
class GraphSegment:
    segment_id: UUID
    revision_id: UUID
    road: RoadSegment


@dataclass(frozen=True)
class Closure:
    tenant_id: UUID
    site_id: UUID
    revision_id: UUID
    segment_id: UUID
    starts_at: datetime
    ends_at: datetime | None


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def available_roads(
    segments: list[GraphSegment],
    closures: list[Closure],
    *,
    tenant_id: UUID,
    site_id: UUID,
    revision_id: UUID,
    departure: datetime,
    horizon: datetime,
) -> list[RoadSegment]:
    """Exclude any road closed during the entire proposed planning window.

    The caller must load a complete trusted closure snapshot and revalidate
    before dispatch. Unknown or invalid relevant closure intervals fail closed.
    A conservative window can exclude roads that would reopen before arrival.
    """
    if not _aware(departure) or not _aware(horizon) or horizon <= departure:
        return []
    blocked: set[UUID] = set()
    for closure in closures:
        if closure.tenant_id != tenant_id or closure.site_id != site_id or closure.revision_id != revision_id:
            continue
        end = closure.ends_at
        if (
            not _aware(closure.starts_at)
            or (end is not None and (not _aware(end) or end <= closure.starts_at))
            or (closure.starts_at <= horizon and (end is None or end > departure))
        ):
            blocked.add(closure.segment_id)
    scoped = [
        item
        for item in segments
        if item.revision_id == revision_id
        and item.road.tenant_id == tenant_id
        and item.road.site_id == site_id
    ]
    seen: set[UUID] = set()
    duplicates: set[UUID] = set()
    for item in scoped:
        if item.segment_id in seen:
            duplicates.add(item.segment_id)
        seen.add(item.segment_id)
    return [
        replace(item.road, segment_id=item.segment_id)
        for item in scoped
        if item.segment_id not in blocked and item.segment_id not in duplicates and item.road.open_for_vehicle
    ]
