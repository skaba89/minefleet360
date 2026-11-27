from dataclasses import replace
from uuid import UUID

from app.dispatch.mining_closures import GraphSegment
from app.dispatch.mining_restrictions import RoadRestriction, VehicleProfile, restrict_roads
from app.dispatch.mining_routes import RoadSegment

TENANT, SITE, REV, SEG, A, B, CATEGORY, OTHER = (UUID(int=i) for i in range(1, 9))
EDGE = GraphSegment(SEG, REV, RoadSegment(TENANT, SITE, A, B, 1000, 60, True))
VEHICLE = VehicleProfile(TENANT, SITE, CATEGORY, 40000)
POLICY = RoadRestriction(TENANT, SITE, REV, SEG, frozenset({CATEGORY}), 40000, 30)


def allowed(
    policies: list[RoadRestriction], vehicle: VehicleProfile = VEHICLE, edge: GraphSegment = EDGE
) -> list[GraphSegment]:
    return restrict_roads([edge], policies, vehicle, revision_id=REV)


def test_speed_ceiling_and_mass_boundary() -> None:
    result = allowed([POLICY])
    assert len(result) == 1
    assert result[0].road.duration_seconds == 120
    assert result[0].road.distance_m == 1000


def test_reference_duration_never_reduced() -> None:
    slow = replace(EDGE, road=replace(EDGE.road, duration_seconds=180))
    assert allowed([POLICY], edge=slow) == [slow]


def test_duration_rounded_up() -> None:
    short = replace(EDGE, road=replace(EDGE.road, distance_m=101, duration_seconds=1))
    assert allowed([POLICY], edge=short)[0].road.duration_seconds == 13


def test_missing_mass_or_overweight_rejected() -> None:
    for mass in (None, 0, -1, 40001):
        assert allowed([POLICY], replace(VEHICLE, gross_mass_kg=mass)) == []


def test_missing_category_or_invalid_speed_rejected() -> None:
    assert allowed([POLICY], replace(VEHICLE, category_id=OTHER)) == []
    assert allowed([replace(POLICY, max_speed_kmh=0)]) == []


def test_missing_duplicate_and_foreign_policy_rejected() -> None:
    assert allowed([]) == []
    assert allowed([POLICY, POLICY]) == []
    assert allowed([replace(POLICY, revision_id=OTHER)]) == []
    assert allowed([replace(POLICY, tenant_id=OTHER)]) == []
    assert allowed([replace(POLICY, site_id=OTHER)]) == []


def test_closed_or_foreign_segment_rejected() -> None:
    closed = replace(EDGE, road=replace(EDGE.road, open_for_vehicle=False))
    assert allowed([POLICY], edge=closed) == []
    assert allowed([POLICY], edge=replace(EDGE, revision_id=OTHER)) == []
    foreign = replace(EDGE, road=replace(EDGE.road, site_id=OTHER))
    assert allowed([POLICY], edge=foreign) == []
