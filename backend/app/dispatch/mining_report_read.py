"""Internal historical report reads, never current readiness or approval."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Row

from app.authz.dependencies import Authorized
from app.authz.principal import evaluate
from app.core.errors import AppError
from app.dispatch.mining_readiness import ReadinessFinding


@dataclass(frozen=True)
class ReportSummary:
    report_id: UUID
    digest_version: str
    evidence_digest: str
    tolerance_m: float
    actor_user_id: UUID
    created_at: datetime
    finding_count: int
    # Approved survey tolerance the report was computed with; grandfathered
    # pre-0091 reports carry None and can never be approved.
    tolerance_qualification_id: UUID | None = None


@dataclass(frozen=True)
class RevisionSummary:
    revision_id: UUID
    version: int
    provenance: str
    created_at: datetime
    report_count: int


@dataclass(frozen=True)
class HistoricalReport:
    summary: ReportSummary
    findings: tuple[ReadinessFinding, ...]


def _require_read(auth: Authorized, site_id: UUID) -> None:
    scope = evaluate(auth.principal, "dispatch.readiness.read")
    if auth.principal.tenant_kind != "CUSTOMER" or scope is None or not scope.covers_site(site_id):
        raise AppError("PERMISSION_DENIED")
    if auth.principal.mfa_enrollment_pending:
        raise AppError("MFA_ENROLLMENT_REQUIRED")


def _summary(row: Row[Any]) -> ReportSummary:
    return ReportSummary(
        row.report_id,
        row.digest_version,
        row.evidence_digest,
        row.tolerance_m,
        row.actor_user_id,
        row.created_at,
        row.finding_count,
        row.tolerance_qualification_id,
    )


def list_readiness_reports(
    auth: Authorized,
    *,
    site_id: UUID,
    revision_id: UUID,
    limit: int = 50,
    before: UUID | None = None,
) -> tuple[list[ReportSummary], UUID | None]:
    """Newest first; resolve cursor inside scope, return a cursor only if more rows exist."""
    _require_read(auth, site_id)
    if not 1 <= limit <= 100:
        raise AppError("VALIDATION_ERROR")
    rows = auth.db.execute(
        text(
            """
            WITH revision AS (
              SELECT revision_id FROM mining_route_revision
              WHERE tenant_id = :tenant AND site_id = :site AND revision_id = :revision
            ), cursor_row AS (
              SELECT created_at, report_id FROM mining_readiness_report
              WHERE tenant_id = :tenant AND site_id = :site AND revision_id = :revision
                AND report_id = :before
            ), reports AS (
              SELECT r.report_id, r.digest_version, r.evidence_digest, r.tolerance_m,
                     r.actor_user_id, r.created_at, jsonb_array_length(r.findings) AS finding_count,
                     r.tolerance_qualification_id
              FROM mining_readiness_report r JOIN revision USING (revision_id)
              WHERE r.tenant_id = :tenant AND r.site_id = :site
                AND (CAST(:before AS uuid) IS NULL OR (r.created_at, r.report_id) <
                     (SELECT created_at, report_id FROM cursor_row))
              ORDER BY r.created_at DESC, r.report_id DESC LIMIT :limit
            )
            SELECT p.*, EXISTS (SELECT 1 FROM cursor_row) AS cursor_found
            FROM revision LEFT JOIN reports p ON true
            ORDER BY p.created_at DESC, p.report_id DESC
            """
        ),
        {
            "tenant": auth.tenant_id,
            "site": site_id,
            "revision": revision_id,
            "before": before,
            "limit": limit + 1,
        },
    ).all()
    if not rows or (before is not None and not rows[0].cursor_found):
        raise AppError("NOT_FOUND")
    summaries = [_summary(row) for row in rows if row.report_id is not None]
    return summaries[:limit], summaries[limit - 1].report_id if len(summaries) > limit else None


def list_site_revisions(
    auth: Authorized,
    *,
    site_id: UUID,
    limit: int = 50,
) -> list[RevisionSummary]:
    """Survey revisions of one site, newest version first, with their recorded report counts."""
    _require_read(auth, site_id)
    if not 1 <= limit <= 100:
        raise AppError("VALIDATION_ERROR")
    site_exists = auth.db.execute(
        text("SELECT 1 FROM site WHERE tenant_id = :tenant AND site_id = :site"),
        {"tenant": auth.tenant_id, "site": site_id},
    ).scalar()
    if site_exists is None:
        # Un site d'un autre tenant est indiscernable d'un identifiant inexistant (isolation ST-02).
        raise AppError("NOT_FOUND")
    rows = auth.db.execute(
        text(
            """
            SELECT v.revision_id, v.version, v.provenance, v.created_at,
                   (SELECT count(*) FROM mining_readiness_report r
                    WHERE r.tenant_id = v.tenant_id AND r.site_id = v.site_id
                      AND r.revision_id = v.revision_id) AS report_count
            FROM mining_route_revision v
            WHERE v.tenant_id = :tenant AND v.site_id = :site
            ORDER BY v.version DESC LIMIT :limit
            """
        ),
        {"tenant": auth.tenant_id, "site": site_id, "limit": limit},
    ).all()
    return [
        RevisionSummary(row.revision_id, row.version, row.provenance, row.created_at, row.report_count)
        for row in rows
    ]


def get_readiness_report(
    auth: Authorized, *, site_id: UUID, revision_id: UUID, report_id: UUID
) -> HistoricalReport:
    """Read one immutable report without treating its findings as live road state."""
    _require_read(auth, site_id)
    row = auth.db.execute(
        text(
            """
            SELECT report_id, digest_version, evidence_digest, tolerance_m, actor_user_id, created_at,
                   jsonb_array_length(findings) AS finding_count, tolerance_qualification_id,
                   CASE WHEN jsonb_array_length(findings) <= 3000 THEN findings END AS findings
            FROM mining_readiness_report
            WHERE tenant_id = :tenant AND site_id = :site AND revision_id = :revision
              AND report_id = :report
            """
        ),
        {"tenant": auth.tenant_id, "site": site_id, "revision": revision_id, "report": report_id},
    ).one_or_none()
    if row is None:
        raise AppError("NOT_FOUND")
    if row.findings is None:
        raise AppError("CONFLICT")
    findings: list[ReadinessFinding] = []
    for item in row.findings:
        if (
            not isinstance(item, dict)
            or set(item) != {"code", "segment_id"}
            or not isinstance(item["code"], str)
            or not 1 <= len(item["code"]) <= 100
            or (item["segment_id"] is not None and not isinstance(item["segment_id"], str))
        ):
            raise AppError("CONFLICT")
        try:
            segment = UUID(item["segment_id"]) if item["segment_id"] is not None else None
        except ValueError as exc:
            raise AppError("CONFLICT") from exc
        findings.append(ReadinessFinding(item["code"], segment))
    return HistoricalReport(_summary(row), tuple(findings))
