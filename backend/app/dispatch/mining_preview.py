"""Draft-only route preview, never a vehicle authorization or dispatch recommendation."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import text

from app.authz.dependencies import Authorized
from app.authz.principal import evaluate
from app.core.errors import AppError
from app.dispatch.mining_closures import Closure, GraphSegment, available_roads
from app.dispatch.mining_restrictions import RoadRestriction, VehicleProfile, restrict_roads
from app.dispatch.mining_routes import MiningRoute, RoadSegment, shortest_mining_route


def preview_draft_route(
    auth: Authorized,
    *,
    site_id: UUID,
    revision_id: UUID,
    origin_id: UUID,
    destination_id: UUID,
    departure: datetime,
    horizon: datetime,
    vehicle: VehicleProfile | None = None,
) -> MiningRoute | None:
    """Preview topology or compatibility with a supplied hypothetical vehicle profile.

    One SQL statement reads the site, draft revision, roads, closures and
    requested vehicle restrictions under the same PostgreSQL MVCC snapshot.
    Changes after that snapshot still require revalidation; this is not an
    operational dispatch authorization.
    """
    scope = evaluate(auth.principal, "dispatch.readiness.read")
    if auth.principal.tenant_kind != "CUSTOMER" or scope is None or not scope.covers_site(site_id):
        raise AppError("PERMISSION_DENIED")
    if auth.principal.mfa_enrollment_pending:
        raise AppError("MFA_ENROLLMENT_REQUIRED")
    if vehicle is not None and (vehicle.tenant_id != auth.tenant_id or vehicle.site_id != site_id):
        raise AppError("PERMISSION_DENIED")
    params = {
        "tenant": auth.tenant_id,
        "site": site_id,
        "revision": revision_id,
        "include_policies": vehicle is not None,
    }
    rows = auth.db.execute(
        text(
            """
            WITH revision AS (
              SELECT r.revision_id
              FROM mining_route_revision r
              JOIN site s ON s.tenant_id = r.tenant_id AND s.site_id = r.site_id
              WHERE r.tenant_id = :tenant AND r.site_id = :site
                AND r.revision_id = :revision AND r.status = 'DRAFT' AND s.status = 'ACTIVE'
            ), roads AS (
              SELECT segment_id, origin_id, destination_id, distance_m, duration_seconds
              FROM mining_route_segment
              WHERE tenant_id = :tenant AND site_id = :site
                AND revision_id IN (SELECT revision_id FROM revision)
              ORDER BY segment_id LIMIT 1001
            ), closures AS (
              SELECT segment_id, starts_at, ends_at
              FROM mining_route_closure
              WHERE tenant_id = :tenant AND site_id = :site
                AND revision_id IN (SELECT revision_id FROM revision)
              ORDER BY closure_id LIMIT 1001
            ), policies AS (
              SELECT p.segment_id, p.max_gross_mass_kg, p.max_speed_kmh,
                     p.max_height_mm, p.max_width_mm, p.max_length_mm,
                     p.uphill_permille, p.downhill_permille,
                     ARRAY(
                       SELECT a.vehicle_category_id FROM mining_road_allowed_category a
                       JOIN vehicle_category c ON c.tenant_id = a.tenant_id
                         AND c.vehicle_category_id = a.vehicle_category_id AND c.is_active
                       WHERE a.tenant_id = p.tenant_id AND a.site_id = p.site_id
                         AND a.revision_id = p.revision_id AND a.segment_id = p.segment_id
                       ORDER BY a.vehicle_category_id LIMIT 1001
                     ) AS categories
              FROM mining_road_restriction p
              WHERE :include_policies AND p.tenant_id = :tenant AND p.site_id = :site
                AND p.revision_id IN (SELECT revision_id FROM revision)
              ORDER BY p.segment_id LIMIT 1001
            )
            SELECT 'revision' AS kind, revision_id AS segment_id, NULL::uuid AS origin_id,
                   NULL::uuid AS destination_id, NULL::integer AS distance_m,
                   NULL::integer AS duration_seconds, NULL::timestamptz AS starts_at,
                   NULL::timestamptz AS ends_at,
                   NULL::integer AS max_gross_mass_kg, NULL::integer AS max_speed_kmh,
                   NULL::integer AS max_height_mm, NULL::integer AS max_width_mm,
                   NULL::integer AS max_length_mm, NULL::integer AS uphill_permille,
                   NULL::integer AS downhill_permille, NULL::uuid[] AS categories FROM revision
            UNION ALL
            SELECT 'road', segment_id, origin_id, destination_id, distance_m,
                   duration_seconds, NULL::timestamptz, NULL::timestamptz,
                   NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL FROM roads
            UNION ALL
            SELECT 'closure', segment_id, NULL, NULL, NULL, NULL, starts_at, ends_at,
                   NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL FROM closures
            UNION ALL
            SELECT 'policy', segment_id, NULL, NULL, NULL, NULL, NULL, NULL,
                   max_gross_mass_kg, max_speed_kmh, max_height_mm, max_width_mm,
                   max_length_mm, uphill_permille, downhill_permille, categories FROM policies
            """
        ),
        params,
    ).all()
    if not any(row.kind == "revision" for row in rows):
        raise AppError("NOT_FOUND")
    road_rows = [row for row in rows if row.kind == "road"]
    closure_rows = [row for row in rows if row.kind == "closure"]
    if len(road_rows) > 1000 or len(closure_rows) > 1000:
        raise AppError("CONFLICT")
    segments = [
        GraphSegment(
            row.segment_id,
            revision_id,
            RoadSegment(
                auth.tenant_id,
                site_id,
                row.origin_id,
                row.destination_id,
                row.distance_m,
                row.duration_seconds,
                True,
            ),
        )
        for row in road_rows
    ]
    closures = [
        Closure(auth.tenant_id, site_id, revision_id, row.segment_id, row.starts_at, row.ends_at)
        for row in closure_rows
    ]
    if vehicle is not None:
        policy_rows = [row for row in rows if row.kind == "policy"]
        if (
            len(policy_rows) > 1000
            or any(len(row.categories) > 1000 for row in policy_rows)
            or sum(len(row.categories) for row in policy_rows) > 10000
        ):
            raise AppError("CONFLICT")
        restrictions = [
            RoadRestriction(
                auth.tenant_id,
                site_id,
                revision_id,
                row.segment_id,
                frozenset(row.categories),
                row.max_gross_mass_kg,
                row.max_speed_kmh,
                row.max_height_mm,
                row.max_width_mm,
                row.max_length_mm,
                row.uphill_permille,
                row.downhill_permille,
            )
            for row in policy_rows
        ]
        segments = restrict_roads(segments, restrictions, vehicle, revision_id=revision_id)
    roads = available_roads(
        segments,
        closures,
        tenant_id=auth.tenant_id,
        site_id=site_id,
        revision_id=revision_id,
        departure=departure,
        horizon=horizon,
    )
    result = shortest_mining_route(
        roads, tenant_id=auth.tenant_id, site_id=site_id, origin_id=origin_id, destination_id=destination_id
    )
    if result is not None and result.duration_seconds > (horizon - departure).total_seconds():
        return None
    return result
