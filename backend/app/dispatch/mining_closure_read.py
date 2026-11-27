"""Internal read-only closure snapshot for draft graph inspection."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text

from app.authz.dependencies import Authorized
from app.authz.principal import evaluate
from app.core.errors import AppError
from app.organization.contracts import site_in_scope


@dataclass(frozen=True)
class ClosureRow:
    segment_id: UUID
    starts_at: datetime
    ends_at: datetime | None


def load_closures(
    auth: Authorized, site_id: UUID, revision_id: UUID, *, limit: int = 1000
) -> list[ClosureRow]:
    """Return the complete bounded snapshot, never silently truncate.

    Draft inspection only. The caller must revalidate before any dispatch.
    """
    scope = evaluate(auth.principal, "dispatch.location.read")
    if scope is None or not scope.covers_site(site_id):
        raise AppError("PERMISSION_DENIED")
    if auth.principal.mfa_enrollment_pending:
        raise AppError("MFA_ENROLLMENT_REQUIRED")
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    site = site_in_scope(auth.db, scope, site_id)
    if site is None or site.tenant_id != auth.tenant_id or site.status != "ACTIVE":
        raise AppError("NOT_FOUND")
    params = {"tenant": auth.tenant_id, "site": site_id, "revision": revision_id, "limit": limit + 1}
    revision = auth.db.execute(
        text(
            "SELECT revision_id FROM mining_route_revision "
            "WHERE tenant_id = :tenant AND site_id = :site AND revision_id = :revision"
        ),
        params,
    ).scalar_one_or_none()
    if revision is None:
        raise AppError("NOT_FOUND")
    rows = auth.db.execute(
        text(
            "SELECT segment_id, starts_at, ends_at FROM mining_route_closure "
            "WHERE tenant_id = :tenant AND site_id = :site AND revision_id = :revision "
            "ORDER BY closure_id LIMIT :limit"
        ),
        params,
    ).all()
    if len(rows) > limit:
        raise AppError("CONFLICT")
    return [ClosureRow(row.segment_id, row.starts_at, row.ends_at) for row in rows]
