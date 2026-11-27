from dataclasses import replace
from uuid import UUID

from app.dispatch.mining_closures import GraphSegment
from app.dispatch.mining_graph_validation import validate_draft_graph
from app.dispatch.mining_routes import RoadSegment

TENANT, SITE, REV, A, B, C, SEG = (UUID(int=i) for i in range(1, 8))
EDGE = GraphSegment(SEG, REV, RoadSegment(TENANT, SITE, A, B, 100, 20, True))


def validate(nodes: list[UUID], segments: list[GraphSegment]) -> tuple[str, ...]:
    return validate_draft_graph(nodes, segments, tenant_id=TENANT, site_id=SITE, revision_id=REV).issues


def test_valid_directed_graph() -> None:
    assert validate([A, B], [EDGE]) == ()


def test_empty_graph() -> None:
    assert validate([], []) == ("EMPTY_GRAPH",)


def test_duplicate_ids_and_isolated_node() -> None:
    assert validate([A, B, C, A], [EDGE, EDGE]) == (
        "DUPLICATE_NODE",
        "DUPLICATE_SEGMENT",
        "ISOLATED_NODE",
    )


def test_unknown_endpoint() -> None:
    assert "UNKNOWN_ENDPOINT" in validate([A], [EDGE])


def test_invalid_segment() -> None:
    invalid = replace(EDGE, road=replace(EDGE.road, duration_seconds=0))
    assert "INVALID_SEGMENT" in validate([A, B], [invalid])


def test_foreign_revision_and_tenant() -> None:
    assert "OUT_OF_SCOPE_SEGMENT" in validate([A, B], [replace(EDGE, revision_id=C)])
    foreign = replace(EDGE, road=replace(EDGE.road, tenant_id=C))
    assert "OUT_OF_SCOPE_SEGMENT" in validate([A, B], [foreign])


def test_limit() -> None:
    assert validate([UUID(int=i) for i in range(1001)], [EDGE]) == ("GRAPH_LIMIT_EXCEEDED",)
