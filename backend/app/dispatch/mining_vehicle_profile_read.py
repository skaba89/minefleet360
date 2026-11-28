"""Server-side vehicle profile resolution from qualified technical evidence.

The mining_vehicle_profile table is ingested evidence (always DRAFT, versioned);
the latest version wins. No GPS snapping, no operational authorization: the
resolved profile only feeds the advisory restriction evaluation, which fails
closed on missing data.
"""

from uuid import UUID

from sqlalchemy import text

from app.authz.dependencies import Authorized
from app.authz.principal import evaluate
from app.core.errors import AppError
from app.dispatch.mining_restrictions import VehicleProfile


def resolve_vehicle_profile(
    auth: Authorized,
    *,
    site_id: UUID,
    vehicle_id: UUID,
) -> VehicleProfile:
    """Build the advisory profile of a vehicle parked at the requested site.

    One SQL statement reads the vehicle, its active category and its latest
    technical profile under the same PostgreSQL MVCC snapshot. A vehicle from
    another tenant is indistinguishable from a missing one (404); a vehicle
    parked elsewhere is a permission problem (403); missing technical evidence
    or a retired category is an unresolvable reference (422).
    """
    scope = evaluate(auth.principal, "dispatch.readiness.read")
    if auth.principal.tenant_kind != "CUSTOMER" or scope is None or not scope.covers_site(site_id):
        raise AppError("PERMISSION_DENIED")
    if auth.principal.mfa_enrollment_pending:
        raise AppError("MFA_ENROLLMENT_REQUIRED")
    params = {"tenant": auth.tenant_id, "site": site_id, "vehicle": vehicle_id}
    row = auth.db.execute(
        text(
            """
            WITH profile AS (
              SELECT max_gross_mass_kg, height_mm, width_mm, length_mm,
                     max_uphill_permille, max_downhill_permille
              FROM mining_vehicle_profile
              WHERE tenant_id = :tenant AND vehicle_id = :vehicle
              ORDER BY version DESC LIMIT 1
            )
            SELECT v.site_id, v.vehicle_category_id, c.is_active,
                   p.max_gross_mass_kg, p.height_mm, p.width_mm, p.length_mm,
                   p.max_uphill_permille, p.max_downhill_permille
            FROM vehicle v
            JOIN vehicle_category c
              ON c.tenant_id = v.tenant_id AND c.vehicle_category_id = v.vehicle_category_id
            LEFT JOIN profile p ON true
            WHERE v.tenant_id = :tenant AND v.vehicle_id = :vehicle
            """
        ),
        params,
    ).first()
    if row is None:
        raise AppError("NOT_FOUND")
    if row.site_id != site_id:
        raise AppError("PERMISSION_DENIED")
    if not row.is_active or row.max_gross_mass_kg is None:
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "vehicle_id"}])
    return VehicleProfile(
        tenant_id=auth.tenant_id,
        site_id=site_id,
        category_id=row.vehicle_category_id,
        gross_mass_kg=row.max_gross_mass_kg,
        height_mm=row.height_mm,
        width_mm=row.width_mm,
        length_mm=row.length_mm,
        max_uphill_permille=row.max_uphill_permille,
        max_downhill_permille=row.max_downhill_permille,
    )
