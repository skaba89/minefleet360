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


@dataclass(frozen=True)
class MiningRoute:
    nodes: tuple[UUID, ...]
    distance_m: int
    duration_seconds: int


def shortest_mining_route(
    segments: list[RoadSegment],
    *,
    tenant_id: UUID,
    site_id: UUID,
    origin_id: UUID,
    destination_id: UUID,
) -> MiningRoute | None:
    """Find the quickest directed path, breaking ties by distance and node IDs."""
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
    start = (0, 0, (origin_id,))
    queue: list[tuple[int, int, tuple[UUID, ...]]] = [start]
    best = {origin_id: start}
    while queue:
        duration, distance, path = heappop(queue)
        current = path[-1]
        if best[current] != (duration, distance, path):
            continue
        if current == destination_id:
            return MiningRoute(path, distance, duration)
        for segment in graph[current]:
            target = segment.destination_id
            candidate = (
                duration + segment.duration_seconds,
                distance + segment.distance_m,
                (*path, target),
            )
            if target not in best or candidate < best[target]:
                best[target] = candidate
                heappush(queue, candidate)
    return None
