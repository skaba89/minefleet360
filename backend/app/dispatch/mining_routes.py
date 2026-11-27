"""Pure advisory routing over explicitly authorized, surveyed mining road segments.

No GPS snapping, persistence or road access authorization is performed here.
The caller must provide a trusted, current graph for the requested tenant/site.
"""

from collections import defaultdict
from dataclasses import dataclass
from heapq import heappop, heappush
from uuid import UUID


@dataclass(frozen=True)
class RoadSegment:
    tenant_id: UUID
    site_id: UUID
    origin_id: UUID
    destination_id: UUID
    distance_m: int
    duration_seconds: int
    open_for_vehicle: bool
    segment_id: UUID | None = None


@dataclass(frozen=True)
class MiningRoute:
    nodes: tuple[UUID, ...]
    distance_m: int
    duration_seconds: int
    segment_ids: tuple[UUID, ...] = ()


def shortest_mining_route(
    segments: list[RoadSegment],
    *,
    tenant_id: UUID,
    site_id: UUID,
    origin_id: UUID,
    destination_id: UUID,
) -> MiningRoute | None:
    """Find the quickest directed path, breaking ties by distance, node IDs and segment IDs."""
    graph: dict[UUID, list[RoadSegment]] = defaultdict(list)
    nodes: set[UUID] = set()
    for segment in segments:
        if segment.tenant_id != tenant_id or segment.site_id != site_id:
            continue
        if (
            not segment.open_for_vehicle
            or segment.distance_m <= 0
            or segment.duration_seconds <= 0
            or segment.origin_id == segment.destination_id
        ):
            continue
        graph[segment.origin_id].append(segment)
        nodes.update((segment.origin_id, segment.destination_id))
    if origin_id not in nodes or destination_id not in nodes:
        return None
    start = (0, 0, (origin_id,), ())
    queue: list[tuple[int, int, tuple[UUID, ...], tuple[int, ...]]] = [start]
    best: dict[UUID, tuple[int, int, tuple[UUID, ...], tuple[int, ...]]] = {origin_id: start}
    while queue:
        duration, distance, path, trace = heappop(queue)
        current = path[-1]
        if best[current] != (duration, distance, path, trace):
            continue
        if current == destination_id:
            segment_ids = tuple(UUID(int=value) for value in trace) if all(value >= 0 for value in trace) else ()
            return MiningRoute(path, distance, duration, segment_ids)
        for segment in graph[current]:
            target = segment.destination_id
            candidate = (
                duration + segment.duration_seconds,
                distance + segment.distance_m,
                (*path, target),
                (*trace, segment.segment_id.int if segment.segment_id is not None else -1),
            )
            if target not in best or candidate < best[target]:
                best[target] = candidate
                heappush(queue, candidate)
    return None
