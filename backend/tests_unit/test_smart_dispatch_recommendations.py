from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.assignment.contracts import AssignmentFacts
from app.dispatch.smart_eta import RouteEstimate
from app.dispatch.smart_recommendations import recommend_from_pool

TENANT = UUID(int=1)
SITE = UUID(int=2)
DESTINATION = UUID(int=3)
NOW = datetime(2026, 11, 27, tzinfo=UTC)


def facts(i: int) -> AssignmentFacts:
    return AssignmentFacts(UUID(int=i), SITE, UUID(int=i + 10), UUID(int=i + 20), "ACTIVE", NOW, None)


def route(i: int, seconds: int) -> RouteEstimate:
    return RouteEstimate(TENANT, SITE, UUID(int=i + 10), DESTINATION, NOW, NOW, NOW, 1000, seconds)


def recommend(pool: list[AssignmentFacts], routes: list[RouteEstimate]) -> list[UUID]:
    result = recommend_from_pool(
        pool, routes, tenant_id=TENANT, site_id=SITE, destination_id=DESTINATION, now=NOW
    )
    return [item.assignment_id for item in result]


def test_rank_valid_candidates() -> None:
    assert recommend([facts(4), facts(5)], [route(4, 120), route(5, 60)]) == [UUID(int=5), UUID(int=4)]


def test_missing_duplicate_and_stale_routes() -> None:
    stale = replace(route(6, 60), position_recorded_at=NOW - timedelta(minutes=3))
    assert recommend([facts(4), facts(5), facts(6)], [route(4, 60), route(4, 90), stale]) == []


def test_wrong_scope_and_expired_assignment() -> None:
    expired = replace(facts(4), valid_to=NOW)
    foreign = replace(route(5, 60), tenant_id=UUID(int=99))
    assert recommend([expired, facts(5)], [route(4, 60), foreign]) == []


def test_route_for_unselected_vehicle_is_ignored() -> None:
    assert recommend([facts(4)], [route(5, 60)]) == []
