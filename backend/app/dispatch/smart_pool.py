"""Read-only candidate pool for immediate dispatch; no ETA or reservation is inferred."""

from uuid import UUID

from sqlalchemy import exists, select

from app.assignment.contracts import AssignmentFacts, running_blockers
from app.assignment.models import VehicleAssignment
from app.authz.dependencies import Authorized
from app.authz.principal import evaluate
from app.core.errors import AppError
from app.dispatch.models import Mission
from app.organization.contracts import site_in_scope


def eligible_pool(auth: Authorized, site_id: UUID, *, limit: int = 100) -> list[AssignmentFacts]:
    """Return a bounded pool, not a guarantee of availability at assignment time.

    Require mission creation and assignment reading on the same site. Any nonterminal
    mission occupying the vehicle or driver excludes the assignment conservatively.
    """
    for permission in ("dispatch.mission.create", "assignment.vehicle_assignment.read"):
        scope = evaluate(auth.principal, permission)
        if scope is None or not scope.covers_site(site_id):
            raise AppError("PERMISSION_DENIED")
    site = site_in_scope(auth.db, auth.scope, site_id)
    if site is None or site.tenant_id != auth.tenant_id or site.status != "ACTIVE":
        raise AppError("NOT_FOUND")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    now = auth.clock.now()
    busy = exists().where(
        Mission.tenant_id == VehicleAssignment.tenant_id,
        Mission.status.not_in(("COMPLETED", "CANCELLED")),
        (Mission.vehicle_id == VehicleAssignment.vehicle_id)
        | (Mission.driver_id == VehicleAssignment.driver_id),
    )
    stmt = (
        select(VehicleAssignment)
        .where(
            VehicleAssignment.tenant_id == auth.tenant_id,
            VehicleAssignment.site_id == site_id,
            VehicleAssignment.status == "ACTIVE",
            VehicleAssignment.valid_from <= now,
            (VehicleAssignment.valid_to.is_(None)) | (VehicleAssignment.valid_to > now),
            ~busy,
        )
        .order_by(VehicleAssignment.vehicle_assignment_id)
        .limit(limit)
    )
    result: list[AssignmentFacts] = []
    for row in auth.db.execute(stmt).scalars():
        facts = AssignmentFacts(
            row.vehicle_assignment_id,
            row.site_id,
            row.vehicle_id,
            row.driver_id,
            row.status,
            row.valid_from,
            row.valid_to,
        )
        if not running_blockers(auth.db, facts, now):
            result.append(facts)
    return result
