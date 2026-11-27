"""Draft survey length inspection; no publication or vehicle authorization."""

from dataclasses import dataclass
from math import isfinite
from uuid import UUID

from sqlalchemy import text

from app.authz.dependencies import Authorized
from app.authz.principal import evaluate
from app.core.errors import AppError


@dataclass(frozen=True)
class LengthFinding:
    segment_id: UUID
    declared_m: int
    measured_m: float
    within_tolerance: bool


def inspect_draft_lengths(
    auth: Authorized,
    *,
    site_id: UUID,
    revision_id: UUID,
    tolerance_m: float,
) -> list[LengthFinding]:
    """Compare against spheroidal path length, with explicit survey tolerance.

    A complete bounded draft snapshot is required. The caller must qualify the
    tolerance for the survey; a passing comparison is not a road safety approval.
    """
    scope = evaluate(auth.principal, "dispatch.location.read")
    if auth.principal.tenant_kind != "CUSTOMER" or scope is None or not scope.covers_site(site_id):
        raise AppError("PERMISSION_DENIED")
    if auth.principal.mfa_enrollment_pending:
        raise AppError("MFA_ENROLLMENT_REQUIRED")
    if not isfinite(tolerance_m) or tolerance_m < 0:
        raise ValueError("tolerance must be finite and nonnegative")
    rows = auth.db.execute(
        text(
            """
            WITH revision AS (
              SELECT r.revision_id FROM mining_route_revision r
              JOIN site s ON s.tenant_id = r.tenant_id AND s.site_id = r.site_id
              WHERE r.tenant_id = :tenant AND r.site_id = :site
                AND r.revision_id = :revision AND r.status = 'DRAFT' AND s.status = 'ACTIVE'
            ), segments AS (
              SELECT segment_id, distance_m, ST_Length(path::geography, true) AS measured_m
              FROM mining_route_segment
              WHERE tenant_id = :tenant AND site_id = :site
                AND revision_id IN (SELECT revision_id FROM revision)
              ORDER BY segment_id LIMIT 1001
            )
            SELECT 'revision' AS kind, revision_id AS segment_id,
                   NULL::integer AS distance_m, NULL::double precision AS measured_m FROM revision
            UNION ALL
            SELECT 'segment', segment_id, distance_m, measured_m FROM segments
            """
        ),
        {"tenant": auth.tenant_id, "site": site_id, "revision": revision_id},
    ).all()
    if not any(row.kind == "revision" for row in rows):
        raise AppError("NOT_FOUND")
    segments = [row for row in rows if row.kind == "segment"]
    if len(segments) > 1000:
        raise AppError("CONFLICT")
    findings: list[LengthFinding] = []
    for row in segments:
        measured = float(row.measured_m)
        valid = (
            isfinite(measured)
            and measured > 0
            and row.distance_m > 0
            and abs(measured - row.distance_m) <= tolerance_m
        )
        findings.append(LengthFinding(row.segment_id, row.distance_m, measured, valid))
    return findings
