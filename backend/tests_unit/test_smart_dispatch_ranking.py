from dataclasses import replace
from uuid import UUID

from app.dispatch.smart_ranking import DispatchCandidate, rank_candidates

TENANT = UUID(int=1)
SITE = UUID(int=2)


def candidate(identifier: int, eta: int | None = 10, idle: int = 0) -> DispatchCandidate:
    return DispatchCandidate(UUID(int=identifier), TENANT, SITE, True, True, True, eta, idle)


def test_rank_is_deterministic() -> None:
    items = [candidate(5, 10, 3), candidate(4, 10, 3), candidate(3, 5), candidate(6, 10, 8)]
    expected = [3, 6, 4, 5]
    for order in (items, list(reversed(items))):
        ranked = rank_candidates(order, tenant_id=TENANT, site_id=SITE)
        assert [item.assignment_id.int for item in ranked] == expected


def test_unsafe_or_unknown_candidates_excluded() -> None:
    items = [
        replace(candidate(3), eligible=False),
        replace(candidate(4), available=False),
        replace(candidate(5), facts_fresh=False),
        candidate(6, None),
        candidate(7, -1),
        candidate(8, 10, -1),
        replace(candidate(9), tenant_id=UUID(int=90)),
        replace(candidate(10), site_id=UUID(int=91)),
        candidate(11),
        candidate(11, 20),
        candidate(12),
    ]
    assert rank_candidates(items, tenant_id=TENANT, site_id=SITE) == [candidate(12)]


def test_empty_input() -> None:
    assert rank_candidates([], tenant_id=TENANT, site_id=SITE) == []
