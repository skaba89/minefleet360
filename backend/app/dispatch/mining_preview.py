"""Draft-only route preview, never a vehicle authorization or dispatch recommendation."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import text

from app.authz.dependencies import Authorized
from app.authz.principal import evaluate
from app.core.errors import AppError
from app.dispatch.mining_closures import Closure, GraphSegment, available_roads
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
) -> MiningRoute | None:
    """Preview topology and reference durations, not vehicle-specific feasibility.

    One SQL statement reads the site, draft revision, roads and closures under
    the same PostgreSQL MVCC snapshot. Changes after that snapshot still require
    revalidation; this is not an operational dispatch authorization.
    """
    scope = evaluate(auth.principal, "dispatch.location.read")
    if auth.principal.tenant_kind != "CUSTOMER" or scope is None or not scope.covers_site(site_id):
        raise AppError("PERMISSION_DENIED")
    if auth.principal.mfa_enrollment_pending:
        raise AppError("MFA_ENROLLMENT_REQUIRED")
    params = {"tenant": auth.tenant_id, "site": site_id, "revision": revision_id}
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
            )
            SELECT 'revision' AS kind, revision_id AS segment_id, NULL::uuid AS origin_id,
                   NULL::uuid AS destination_id, NULL::integer AS distance_m,
                   NULL::integer AS duration_seconds, NULL::timestamptz AS starts_at,
                   NULL::timestamptz AS ends_at FROM revision
            UNION ALL
            SELECT 'road', segment_id, origin_id, destination_id, distance_m,
                   duration_seconds, NULL::timestamptz, NULL::timestamptz FROM roads
            UNION ALL
            SELECT 'closure', segment_id, NULL, NULL, NULL, NULL, starts_at, ends_at FROM closures
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
