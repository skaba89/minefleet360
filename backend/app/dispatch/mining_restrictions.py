"""Pure restriction evaluation; inputs must come from qualified server-side evidence."""

from dataclasses import dataclass, replace
from uuid import UUID

from app.dispatch.mining_closures import GraphSegment


@dataclass(frozen=True)
class VehicleProfile:
    tenant_id: UUID
    site_id: UUID
    category_id: UUID
    gross_mass_kg: int | None
    height_mm: int | None = None
    width_mm: int | None = None
    length_mm: int | None = None


@dataclass(frozen=True)
class RoadRestriction:
    tenant_id: UUID
    site_id: UUID
    revision_id: UUID
    segment_id: UUID
    allowed_categories: frozenset[UUID]
    max_gross_mass_kg: int
    max_speed_kmh: int
    max_height_mm: int | None = None
    max_width_mm: int | None = None
    max_length_mm: int | None = None


def _fits_dimension(actual: int | None, ceiling: int | None) -> bool:
    return actual is not None and ceiling is not None and 0 < actual <= ceiling


def restrict_roads(
    segments: list[GraphSegment],
    restrictions: list[RoadRestriction],
    vehicle: VehicleProfile,
    *,
    revision_id: UUID,
    require_dimensions: bool = True,
) -> list[GraphSegment]:
    """Fail closed for missing/ambiguous restrictions or unverified gross mass.

    Reference durations may only increase to respect the speed ceiling.
    Nominal payload capacity is not evidence of actual gross vehicle mass.
    Dimensions are required by default. Explicit mass-only previews are not
    evidence of clearance and must never authorize operational dispatch.
    """
    mass = vehicle.gross_mass_kg
    if mass is None or mass <= 0:
        return []
    policies: dict[UUID, RoadRestriction] = {}
    duplicates: set[UUID] = set()
    for rule in restrictions:
        if (
            rule.tenant_id != vehicle.tenant_id
            or rule.site_id != vehicle.site_id
            or rule.revision_id != revision_id
        ):
            continue
        if rule.segment_id in policies:
            duplicates.add(rule.segment_id)
        policies[rule.segment_id] = rule
    result: list[GraphSegment] = []
    for item in segments:
        road = item.road
        if (
            item.revision_id != revision_id
            or road.tenant_id != vehicle.tenant_id
            or road.site_id != vehicle.site_id
            or not road.open_for_vehicle
            or road.distance_m <= 0
            or road.duration_seconds <= 0
        ):
            continue
        policy = policies.get(item.segment_id)
        if (
            policy is None
            or item.segment_id in duplicates
            or vehicle.category_id not in policy.allowed_categories
            or policy.max_gross_mass_kg < mass
            or policy.max_speed_kmh <= 0
        ):
            continue
        if require_dimensions and not (
            _fits_dimension(vehicle.height_mm, policy.max_height_mm)
            and _fits_dimension(vehicle.width_mm, policy.max_width_mm)
            and _fits_dimension(vehicle.length_mm, policy.max_length_mm)
        ):
            continue
        # ceil(distance_m * 3.6 / speed_kmh), using exact integer arithmetic.
        numerator = road.distance_m * 18
        denominator = policy.max_speed_kmh * 5
        minimum_seconds = (numerator + denominator - 1) // denominator
        result.append(
            replace(item, road=replace(road, duration_seconds=max(road.duration_seconds, minimum_seconds)))
        )
    return result
