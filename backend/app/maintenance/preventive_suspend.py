"""Suspension contrôlée d'un plan préventif existant (service interne).

Le verrou de ligne, la version optimiste, le contrôle de site et l'audit sont
appliqués dans la même transaction. Ce service n'expose aucune route HTTP.
"""

import uuid

from sqlalchemy import select

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.core.http import check_version
from app.fleet.models import Vehicle
from app.maintenance.preventive_models import MaintenancePlan
from app.maintenance.preventive_plan_inputs import PreventivePlanSuspend
from app.maintenance.preventive_write import MANAGE_PERMISSION, PREVENTIVE_MANAGE_PERMISSION


def suspend_plan(
    auth: Authorized,
    plan_id: uuid.UUID,
    body: PreventivePlanSuspend,
    expected_version: int,
) -> MaintenancePlan:
    """Suspendre un plan, sans effacer les échéances ou les versions historiques."""
    if auth.scope.permission not in (MANAGE_PERMISSION, PREVENTIVE_MANAGE_PERMISSION):
        raise AppError("PERMISSION_DENIED")

    plan = auth.db.execute(
        select(MaintenancePlan)
        .where(
            MaintenancePlan.tenant_id == auth.tenant_id,
            MaintenancePlan.maintenance_plan_id == plan_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if plan is None:
        raise AppError("NOT_FOUND")

    vehicle = auth.db.execute(
        select(Vehicle).where(
            Vehicle.tenant_id == auth.tenant_id,
            Vehicle.vehicle_id == plan.vehicle_id,
        )
    ).scalar_one_or_none()
    if vehicle is None or not auth.scope.covers_site(vehicle.site_id):
        raise AppError("NOT_FOUND")

    check_version(expected_version, plan.row_version)
    if not plan.active:
        raise AppError("STATE_TRANSITION_INVALID")

    plan.active = False
    plan.suspension_reason = body.reason
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        site_id=vehicle.site_id,
        action="maintenance.plan.suspend",
        entity_type="maintenance_plan",
        entity_id=plan.maintenance_plan_id,
        changed_fields=("active", "suspension_reason"),
    )
    auth.db.commit()
    return plan
