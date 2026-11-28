"""Deterministic locking of mining review sources before any recorded decision.

The readiness report records what the actor saw; a decision may only be written
while the sources it describes are pinned inside the same transaction. This
module locks, in a fixed order, every non-append-only input of the evidence
digest: the site row (status), the vehicle categories referenced by the revision
(is_active) and the revision itself (proxy for all revision-scoped graph rows:
nodes, segments, restrictions, allowed categories).

Locking means: row-level ``FOR SHARE`` where the application role owns UPDATE
(site, vehicle_category) and a transactional advisory lock keyed on the revision
identity everywhere else. The application role deliberately has no UPDATE
privilege on ``mining_route_revision`` (least privilege), so row-level locking
is unavailable there; ``pg_advisory_xact_lock`` requires no privilege, is
released at commit or rollback, and serializes every participant taking the
same derived key.

Writer contract: any write to a revision-scoped mining graph row must first
take the same advisory lock (same derivation from the revision_id) and verify
the revision is DRAFT inside the same transaction; site and vehicle-category
writes are serialized by their own row locks. A decision therefore never closes
a lock cycle with a writer, and a lock on the report alone would protect none
of these concurrent writes.
"""

from uuid import UUID

from sqlalchemy import text

from app.authz.dependencies import Authorized
from app.core.errors import AppError

_SITE_LOCK = text("SELECT 1 FROM site WHERE tenant_id = :tenant AND site_id = :site FOR SHARE")
_CATEGORY_LOCK = text(
    """
    SELECT vc.vehicle_category_id FROM vehicle_category vc
    WHERE vc.tenant_id = :tenant AND vc.vehicle_category_id = ANY (
      SELECT a.vehicle_category_id FROM mining_road_allowed_category a
      WHERE a.tenant_id = :tenant AND a.site_id = :site AND a.revision_id = :revision
    )
    ORDER BY vc.vehicle_category_id FOR SHARE
    """
)
_REVISION_LOCK = text(
    """
    SELECT pg_advisory_xact_lock(
             ('x' || substr(revision_id::text, 1, 8))::bit(32)::int,
             ('x' || substr(revision_id::text, 25, 8))::bit(32)::int
           )
    FROM mining_route_revision
    WHERE tenant_id = :tenant AND site_id = :site AND revision_id = :revision
    """
)


def lock_review_sources(auth: Authorized, *, site_id: UUID, revision_id: UUID) -> None:
    """Pin site, referenced categories, then the revision in the caller's transaction.

    Fixed order site → categories (by id) → revision: every participant takes its
    locks in compatible order, so concurrent decisions serialize without
    deadlock. The advisory-key derivation maps the first and last hexadecimal
    groups of the revision UUID onto the two 32-bit halves; a theoretical key
    collision would only over-serialize unrelated revisions, never corrupt data.
    Missing site or revision is NOT_FOUND; the caller still owns commit and
    rollback.
    """
    params = {"tenant": auth.tenant_id, "site": site_id, "revision": revision_id}
    if auth.db.execute(_SITE_LOCK, params).one_or_none() is None:
        raise AppError("NOT_FOUND")
    auth.db.execute(_CATEGORY_LOCK, params)
    if auth.db.execute(_REVISION_LOCK, params).one_or_none() is None:
        raise AppError("NOT_FOUND")
