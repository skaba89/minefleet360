from dataclasses import replace
from uuid import UUID

from app.dispatch.mining_routes import MiningRoute, RoadSegment, shortest_mining_route

TENANT = UUID(int=1)
SITE = UUID(int=2)
A, B, C, D = (UUID(int=i) for i in range(3, 7))


def edge(origin: UUID, destination: UUID, duration: int, distance: int = 100) -> RoadSegment:
    return RoadSegment(TENANT, SITE, origin, destination, distance, duration, True)


def route(segments: list[RoadSegment], origin: UUID = A, destination: UUID = D) -> MiningRoute | None:
    return shortest_mining_route(
        segments, tenant_id=TENANT, site_id=SITE, origin_id=origin, destination_id=destination
    )


def test_quickest_route_not_shortest_distance() -> None:
    segments = [edge(A, D, 100, 50), edge(A, B, 10), edge(B, D, 20)]
    assert route(segments) == MiningRoute((A, B, D), 200, 30)


def test_closed_and_foreign_segments_excluded() -> None:
    segments = [
        replace(edge(A, D, 1), open_for_vehicle=False),
        replace(edge(A, D, 1), tenant_id=UUID(int=99)),
        replace(edge(A, D, 1), site_id=UUID(int=99)),
        edge(A, B, 10),
        edge(B, D, 20),
    ]
    assert route(segments) == MiningRoute((A, B, D), 200, 30)


def test_one_way_and_disconnected_graph() -> None:
    assert route([edge(D, A, 10)]) is None
    assert route([edge(A, B, 10), edge(C, D, 20)]) is None


def test_invalid_segments_excluded() -> None:
    assert route([edge(A, D, 0), edge(A, D, 10, -1), edge(A, D, -1)]) is None


def test_tie_break_is_deterministic_and_cycles_safe() -> None:
    segments = [edge(A, C, 10), edge(C, D, 20), edge(A, B, 10), edge(B, D, 20), edge(B, A, 1)]
    expected = MiningRoute((A, B, D), 200, 30)
    assert route(segments) == expected
    assert route(list(reversed(segments))) == expected


def test_known_origin_equals_destination() -> None:
    assert route([edge(A, B, 10)], A, A) == MiningRoute((A,), 0, 0)
    assert route([], A, A) is None
