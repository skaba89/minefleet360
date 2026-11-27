"""Internal draft restriction reader, not an operational authorization."""

from uuid import UUID

from sqlalchemy import text

from app.authz.dependencies import Authorized
from app.authz.principal import evaluate
from app.core.errors import AppError
from app.dispatch.mining_restrictions import RoadRestriction


def load_draft_restrictions(auth: Authorized, site_id: UUID, revision_id: UUID) -> list[RoadRestriction]:
    """Read complete bounded restrictions and active category allowlists.

    Unknown dimensions and grades are preserved. This snapshot alone cannot
    authorize dispatch; graph and closures must ultimately share its snapshot.
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
            ), categories AS (
              SELECT a.segment_id, a.vehicle_category_id
              FROM mining_road_allowed_category a
              JOIN vehicle_category c ON c.tenant_id = a.tenant_id
                AND c.vehicle_category_id = a.vehicle_category_id AND c.is_active
              WHERE a.tenant_id = :tenant AND a.site_id = :site
                AND a.revision_id IN (SELECT revision_id FROM revision)
              ORDER BY a.segment_id, a.vehicle_category_id LIMIT 10001
            )
            SELECT 'revision' AS kind, revision_id AS segment_id,
                   NULL::integer AS max_gross_mass_kg, NULL::integer AS max_speed_kmh,
                   NULL::integer AS max_height_mm, NULL::integer AS max_width_mm,
                   NULL::integer AS max_length_mm, NULL::integer AS uphill_permille,
                   NULL::integer AS downhill_permille, NULL::uuid AS category_id FROM revision
            UNION ALL
            SELECT 'policy', segment_id, max_gross_mass_kg, max_speed_kmh,
                   max_height_mm, max_width_mm, max_length_mm, uphill_permille,
                   downhill_permille, NULL::uuid FROM policies
            UNION ALL
            SELECT 'category', segment_id, NULL, NULL, NULL, NULL, NULL, NULL,
                   NULL, vehicle_category_id FROM categories
            """
        ),
        {"tenant": auth.tenant_id, "site": site_id, "revision": revision_id},
    ).all()
    if not any(row.kind == "revision" for row in rows):
        raise AppError("NOT_FOUND")
    policies = [row for row in rows if row.kind == "policy"]
    categories = [row for row in rows if row.kind == "category"]
    if len(policies) > 1000 or len(categories) > 10000:
        raise AppError("CONFLICT")
    allowed: dict[UUID, set[UUID]] = {}
    for row in categories:
        allowed.setdefault(row.segment_id, set()).add(row.category_id)
    return [
        RoadRestriction(
            tenant_id=auth.tenant_id,
            site_id=site_id,
            revision_id=revision_id,
            segment_id=row.segment_id,
            allowed_categories=frozenset(allowed.get(row.segment_id, set())),
            max_gross_mass_kg=row.max_gross_mass_kg,
            max_speed_kmh=row.max_speed_kmh,
            max_height_mm=row.max_height_mm,
            max_width_mm=row.max_width_mm,
            max_length_mm=row.max_length_mm,
            uphill_permille=row.uphill_permille,
            downhill_permille=row.downhill_permille,
        )
        for row in policies
    ]
