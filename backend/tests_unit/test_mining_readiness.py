from dataclasses import replace
from uuid import UUID

from app.dispatch.mining_closures import GraphSegment
from app.dispatch.mining_geodesic import LengthFinding
from app.dispatch.mining_readiness import ReadinessFinding, inspect_readiness
from app.dispatch.mining_restrictions import RoadRestriction
from app.dispatch.mining_routes import RoadSegment

TENANT, SITE, REV, A, B, SEG, CATEGORY, OTHER = (UUID(int=i) for i in range(1, 9))
EDGE = GraphSegment(SEG, REV, RoadSegment(TENANT, SITE, A, B, 100, 20, True))
RULE = RoadRestriction(TENANT, SITE, REV, SEG, frozenset({CATEGORY}), 40000, 30, 4500, 3500, 13000, 80, 0)
LENGTH = LengthFinding(SEG, 100, 101.0, True)


def inspect(rules: list[RoadRestriction], lengths: list[LengthFinding]) -> tuple[ReadinessFinding, ...]:
    return inspect_readiness([A, B], [EDGE], rules, lengths, tenant_id=TENANT, site_id=SITE, revision_id=REV)


def test_complete_evidence() -> None:
    assert inspect([RULE], [LENGTH]) == ()


def test_missing_evidence() -> None:
    assert inspect([], []) == (
        ReadinessFinding("MISSING_RESTRICTION", SEG),
        ReadinessFinding("MISSING_OR_FAILED_LENGTH_CHECK", SEG),
    )


def test_unknown_dimensions_grades_or_categories() -> None:
    for rule in (
        replace(RULE, max_height_mm=None),
        replace(RULE, downhill_permille=None),
        replace(RULE, allowed_categories=frozenset()),
    ):
        assert inspect([rule], [LENGTH]) == (ReadinessFinding("INCOMPLETE_RESTRICTION", SEG),)


def test_failed_length_check() -> None:
    assert inspect([RULE], [replace(LENGTH, within_tolerance=False)]) == (
        ReadinessFinding("MISSING_OR_FAILED_LENGTH_CHECK", SEG),
    )


def test_duplicate_and_foreign_evidence() -> None:
    assert ReadinessFinding("FOREIGN_RESTRICTION", SEG) in inspect(
        [RULE, replace(RULE, tenant_id=OTHER)], [LENGTH]
    )
    assert ReadinessFinding("UNEXPECTED_OR_DUPLICATE_RESTRICTION", SEG) in inspect([RULE, RULE], [LENGTH])
    assert ReadinessFinding("UNEXPECTED_OR_DUPLICATE_LENGTH", SEG) in inspect([RULE], [LENGTH, LENGTH])
