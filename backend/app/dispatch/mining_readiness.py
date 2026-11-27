"""Pure technical readiness checks; never an approval or dispatch authorization."""

from dataclasses import dataclass
from uuid import UUID

from app.dispatch.mining_closures import GraphSegment
from app.dispatch.mining_geodesic import LengthFinding
from app.dispatch.mining_graph_validation import validate_draft_graph
from app.dispatch.mining_restrictions import RoadRestriction


@dataclass(frozen=True)
class ReadinessFinding:
    code: str
    segment_id: UUID | None = None


def inspect_readiness(
    nodes: list[UUID],
    segments: list[GraphSegment],
    restrictions: list[RoadRestriction],
    lengths: list[LengthFinding],
    *,
    tenant_id: UUID,
    site_id: UUID,
    revision_id: UUID,
) -> tuple[ReadinessFinding, ...]:
    """Require complete evidence from one trusted snapshot; no approval is written."""
    if any(len(items) > 1000 for items in (nodes, segments, restrictions, lengths)):
        return (ReadinessFinding("GRAPH_LIMIT_EXCEEDED"),)
    graph = validate_draft_graph(
        nodes, segments, tenant_id=tenant_id, site_id=site_id, revision_id=revision_id
    )
    findings = [ReadinessFinding(code) for code in graph.issues]
    known = {item.segment_id for item in segments}
    policies: dict[UUID, RoadRestriction] = {}
    measured: dict[UUID, LengthFinding] = {}
    for supplied_rule in restrictions:
        key = supplied_rule.segment_id
        if (supplied_rule.tenant_id, supplied_rule.site_id, supplied_rule.revision_id) != (
            tenant_id,
            site_id,
            revision_id,
        ):
            findings.append(ReadinessFinding("FOREIGN_RESTRICTION", key))
            continue
        if key not in known or key in policies:
            findings.append(ReadinessFinding("UNEXPECTED_OR_DUPLICATE_RESTRICTION", key))
            continue
        policies[key] = supplied_rule
    for supplied_length in lengths:
        key = supplied_length.segment_id
        if key not in known or key in measured:
            findings.append(ReadinessFinding("UNEXPECTED_OR_DUPLICATE_LENGTH", key))
            continue
        measured[key] = supplied_length
    for key in sorted(known):
        rule = policies.get(key)
        if rule is None:
            findings.append(ReadinessFinding("MISSING_RESTRICTION", key))
        elif (
            not rule.allowed_categories
            or rule.max_gross_mass_kg <= 0
            or rule.max_speed_kmh <= 0
            or any(
                value is None or value <= 0
                for value in (rule.max_height_mm, rule.max_width_mm, rule.max_length_mm)
            )
            or any(value is None or value < 0 for value in (rule.uphill_permille, rule.downhill_permille))
        ):
            findings.append(ReadinessFinding("INCOMPLETE_RESTRICTION", key))
        length = measured.get(key)
        if length is None or not length.within_tolerance:
            findings.append(ReadinessFinding("MISSING_OR_FAILED_LENGTH_CHECK", key))
    return tuple(findings)
