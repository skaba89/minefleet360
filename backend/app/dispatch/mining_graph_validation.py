"""Pure structural checks for a draft graph; not a publication authorization."""

from dataclasses import dataclass
from uuid import UUID

from app.dispatch.mining_closures import GraphSegment


@dataclass(frozen=True)
class GraphValidation:
    issues: tuple[str, ...]

    @property
    def structurally_valid(self) -> bool:
        return not self.issues


def validate_draft_graph(
    nodes: list[UUID],
    segments: list[GraphSegment],
    *,
    tenant_id: UUID,
    site_id: UUID,
    revision_id: UUID,
) -> GraphValidation:
    """Reject malformed or incomplete topology; no vehicle feasibility is inferred."""
    if len(nodes) > 1000 or len(segments) > 1000:
        return GraphValidation(("GRAPH_LIMIT_EXCEEDED",))
    issues: set[str] = set()
    known = set(nodes)
    if not nodes or not segments:
        issues.add("EMPTY_GRAPH")
    if len(known) != len(nodes):
        issues.add("DUPLICATE_NODE")
    seen: set[UUID] = set()
    connected: set[UUID] = set()
    for item in segments:
        road = item.road
        if item.segment_id in seen:
            issues.add("DUPLICATE_SEGMENT")
        seen.add(item.segment_id)
        if item.revision_id != revision_id or road.tenant_id != tenant_id or road.site_id != site_id:
            issues.add("OUT_OF_SCOPE_SEGMENT")
            continue
        if road.origin_id not in known or road.destination_id not in known:
            issues.add("UNKNOWN_ENDPOINT")
            continue
        if road.origin_id == road.destination_id or road.distance_m <= 0 or road.duration_seconds <= 0:
            issues.add("INVALID_SEGMENT")
            continue
        connected.update((road.origin_id, road.destination_id))
    if known - connected:
        issues.add("ISOLATED_NODE")
    return GraphValidation(tuple(sorted(issues)))
