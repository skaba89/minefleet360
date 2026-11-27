"""Authorized draft restriction inspection, not an operational routing snapshot."""

from uuid import UUID

from sqlalchemy import text

from app.authz.dependencies import Authorized
from app.authz.principal import evaluate
from app.core.errors import AppError
from app.dispatch.mining_restrictions import RoadRestriction


def load_draft_restrictions(auth: Authorized, *, site_id: UUID, revision_id: UUID) -> list[RoadRestriction]:
    """Read policies and category membership in one bounded SQL snapshot.

    Missing categories remain an empty allowlist. Unknown clearances and grades
    stay unknown. A separate graph read is not a coherent operational snapshot.
    """
    scope = evaluate(auth.principal, "dispatch.location.read")
    if auth.principal.tenant_kind != "CUSTOMER" or scope is None or not scope.covers_site(site_id):
        raise AppError("PERMISSION_DENIED")
    if auth.principal.mfa_enrollment_pending:
        raise AppError("MFA_ENROLLMENT_REQUIRED")
    rows = auth.db.execute(
        text(
            """
            WITH revision AS (
              SELECT r.revision_id FROM mining_route_revision r
              JOIN site s ON s.tenant_id = r.tenant_id AND s.site_id = r.site_id
              WHERE r.tenant_id = :tenant AND r.site_id = :site
                AND r.revision_id = :revision AND r.status = 'DRAFT' AND s.status = 'ACTIVE'
            ), policies AS (
              SELECT p.* FROM mining_road_restriction p
              WHERE p.tenant_id = :tenant AND p.site_id = :site
                AND p.revision_id IN (SELECT revision_id FROM revision)
              ORDER BY p.segment_id LIMIT 1001
            )
            SELECT r.revision_id, p.segment_id, p.max_gross_mass_kg, p.max_speed_kmh,
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
            FROM revision r LEFT JOIN policies p ON p.revision_id = r.revision_id
            ORDER BY p.segment_id
            """
        ),
        {"tenant": auth.tenant_id, "site": site_id, "revision": revision_id},
    ).all()
    if not rows:
        raise AppError("NOT_FOUND")
    if (
        len(rows) > 1000
        or any(len(row.categories) > 1000 for row in rows)
        or sum(len(row.categories) for row in rows) > 10000
    ):
        raise AppError("CONFLICT")
    return [
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
        for row in rows
        if row.segment_id is not None
    ]
