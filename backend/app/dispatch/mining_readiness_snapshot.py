"""Inspect a draft with the same PostgreSQL statement snapshot for every check."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Row, text

from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.dispatch.mining_closures import GraphSegment
from app.dispatch.mining_geodesic import check_length, require_draft_inspection
from app.dispatch.mining_readiness import ReadinessFinding, inspect_readiness
from app.dispatch.mining_restrictions import RoadRestriction
from app.dispatch.mining_routes import RoadSegment

# Keep the empty revision row and include isolated nodes. The two bounded
# branches of "items" are disjoint, so nodes never multiply the segment rows.
_SNAPSHOT = text(
    """
    WITH revision AS (
      SELECT r.tenant_id, r.site_id, r.revision_id
      FROM mining_route_revision r JOIN site s USING (tenant_id, site_id)
      WHERE r.tenant_id = :tenant AND r.site_id = :site AND r.revision_id = :revision
        AND r.status = 'DRAFT' AND s.status = 'ACTIVE'
    ), nodes AS (
      SELECT n.node_id FROM mining_route_node n JOIN revision USING (tenant_id, site_id, revision_id)
      ORDER BY n.node_id LIMIT 1001
    ), segments AS (
      SELECT s.segment_id, s.origin_id, s.destination_id, s.distance_m, s.duration_seconds,
             ST_Length(s.path::geography, true) AS measured_m
      FROM mining_route_segment s JOIN revision USING (tenant_id, site_id, revision_id)
      ORDER BY s.segment_id LIMIT 1001
    ), allowed AS (
      SELECT a.segment_id, a.vehicle_category_id FROM mining_road_allowed_category a
      JOIN revision USING (tenant_id, site_id, revision_id)
      JOIN segments USING (segment_id)
      JOIN vehicle_category c USING (tenant_id, vehicle_category_id)
      WHERE c.is_active
      ORDER BY a.segment_id, a.vehicle_category_id LIMIT 10001
    ), categories AS (
      SELECT segment_id, array_agg(vehicle_category_id ORDER BY vehicle_category_id) AS ids
      FROM allowed GROUP BY segment_id
    ), items AS (
      SELECT node_id, NULL::uuid AS segment_id FROM nodes
      UNION ALL
      SELECT NULL::uuid, segment_id FROM segments
    )
    SELECT statement_timestamp() AS inspected_at, i.node_id, s.*, p.segment_id AS policy_id,
           p.max_gross_mass_kg, p.max_speed_kmh,
           p.max_height_mm, p.max_width_mm, p.max_length_mm, p.uphill_permille, p.downhill_permille,
           COALESCE(c.ids, ARRAY[]::uuid[]) AS categories
    FROM revision r LEFT JOIN items i ON true
    LEFT JOIN segments s ON s.segment_id = i.segment_id
    LEFT JOIN categories c ON c.segment_id = s.segment_id
    LEFT JOIN mining_road_restriction p ON p.tenant_id = r.tenant_id AND p.site_id = r.site_id
      AND p.revision_id = r.revision_id AND p.segment_id = s.segment_id
    ORDER BY i.node_id NULLS LAST, s.segment_id
    """
)


def inspect_draft_readiness(
    auth: Authorized, *, site_id: UUID, revision_id: UUID, tolerance_m: float
) -> tuple[ReadinessFinding, ...]:
    """Read-only technical findings for the supplied survey tolerance, prior to human review."""
    rows = read_draft_snapshot(auth, site_id=site_id, revision_id=revision_id, tolerance_m=tolerance_m)
    return evaluate_snapshot(
        rows, tenant_id=auth.tenant_id, site_id=site_id, revision_id=revision_id, tolerance_m=tolerance_m
    )


def read_draft_snapshot(
    auth: Authorized, *, site_id: UUID, revision_id: UUID, tolerance_m: float
) -> Sequence[Row[Any]]:
    require_draft_inspection(auth, site_id, tolerance_m)
    tenant_id = auth.tenant_id
    rows = auth.db.execute(_SNAPSHOT, {"tenant": tenant_id, "site": site_id, "revision": revision_id}).all()
    if not rows:
        raise AppError("NOT_FOUND")
    nodes = [row.node_id for row in rows if row.node_id is not None]
    roads = [row for row in rows if row.segment_id is not None]
    if (
        len(nodes) > 1000
        or len(roads) > 1000
        or any(len(row.categories) > 1000 for row in roads)
        or sum(len(row.categories) for row in roads) > 10000
    ):
        raise AppError("CONFLICT")
    return rows


def evaluate_snapshot(
    rows: Sequence[Row[Any]], *, tenant_id: UUID, site_id: UUID, revision_id: UUID, tolerance_m: float
) -> tuple[ReadinessFinding, ...]:
    nodes = [row.node_id for row in rows if row.node_id is not None]
    roads = [row for row in rows if row.segment_id is not None]
    segments = [
        GraphSegment(
            row.segment_id,
            revision_id,
            RoadSegment(
                tenant_id,
                site_id,
                row.origin_id,
                row.destination_id,
                row.distance_m,
                row.duration_seconds,
                True,
            ),
        )
        for row in roads
    ]
    restrictions = [
        RoadRestriction(
            tenant_id,
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
        for row in roads
        if row.policy_id is not None
    ]
    lengths = [
        check_length(row.segment_id, row.distance_m, float(row.measured_m), tolerance_m) for row in roads
    ]
    return inspect_readiness(
        nodes, segments, restrictions, lengths, tenant_id=tenant_id, site_id=site_id, revision_id=revision_id
    )
