from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.dispatch.mining_closures import Closure, GraphSegment, available_roads
from app.dispatch.mining_routes import MiningRoute, RoadSegment, shortest_mining_route

TENANT, SITE, REV, A, B, C = (UUID(int=i) for i in range(1, 7))
NOW = datetime(2026, 11, 27, tzinfo=UTC)
END = NOW + timedelta(minutes=30)


def segment(i: int, origin: UUID, destination: UUID, duration: int) -> GraphSegment:
    return GraphSegment(UUID(int=i), REV, RoadSegment(TENANT, SITE, origin, destination, 100, duration, True))


DIRECT = segment(10, A, C, 10)
FIRST = segment(11, A, B, 20)
SECOND = segment(12, B, C, 20)
CLOSED = Closure(TENANT, SITE, REV, DIRECT.segment_id, NOW, None)


def roads(closures: list[Closure], segments: list[GraphSegment] | None = None) -> list[RoadSegment]:
    return available_roads(
        [DIRECT, FIRST, SECOND] if segments is None else segments,
        closures,
        tenant_id=TENANT,
        site_id=SITE,
        revision_id=REV,
        departure=NOW,
        horizon=END,
    )


def test_closure_forces_alternative() -> None:
    result = shortest_mining_route(
        roads([CLOSED]), tenant_id=TENANT, site_id=SITE, origin_id=A, destination_id=C
    )
    assert result == MiningRoute((A, B, C), 200, 40)


def test_future_closure_inside_window_blocks_road() -> None:
    assert DIRECT.road not in roads([replace(CLOSED, starts_at=NOW + timedelta(minutes=5))])


def test_expired_and_later_closures_do_not_block() -> None:
    expired = replace(CLOSED, starts_at=NOW - timedelta(hours=1), ends_at=NOW)
    later = replace(CLOSED, starts_at=END + timedelta(seconds=1))
    assert DIRECT.road in roads([expired, later])


def test_foreign_closure_does_not_block() -> None:
    assert DIRECT.road in roads([replace(CLOSED, tenant_id=UUID(int=99))])
    assert DIRECT.road in roads([replace(CLOSED, revision_id=UUID(int=99))])


def test_invalid_closure_fails_closed() -> None:
    assert DIRECT.road not in roads([replace(CLOSED, ends_at=NOW)])
    assert DIRECT.road not in roads([replace(CLOSED, starts_at=NOW.replace(tzinfo=None))])


def test_duplicate_segment_and_foreign_graph_excluded() -> None:
    assert roads([], [DIRECT, DIRECT, replace(FIRST, revision_id=UUID(int=99))]) == []
