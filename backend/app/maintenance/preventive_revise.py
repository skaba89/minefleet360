"""Révision interne de plans préventifs avec historique immuable des seuils."""

import uuid

from sqlalchemy import select

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.core.http import check_version
from app.fleet.models import Vehicle
from app.maintenance.preventive_models import MaintenancePlan
from app.maintenance.preventive_plan_inputs import PreventivePlanCreate
from app.maintenance.preventive_write import MANAGE_PERMISSION, PREVENTIVE_MANAGE_PERMISSION


def revise_plan(
    auth: Authorized,
    plan_id: uuid.UUID,
    body: PreventivePlanCreate,
    expected_version: int,
) -> MaintenancePlan:
    """Créer une nouvelle version sans modifier les seuils de l'ancienne.

    Le service doit être appelé par une route avec Require(MANAGE_PERMISSION).
    La contrainte d'unicité partielle en base prévient deux versions actives.
    """
    if auth.scope.permission not in (MANAGE_PERMISSION, PREVENTIVE_MANAGE_PERMISSION):
        raise AppError("PERMISSION_DENIED")

    current = auth.db.execute(
        select(MaintenancePlan)
        .where(
            MaintenancePlan.tenant_id == auth.tenant_id,
            MaintenancePlan.maintenance_plan_id == plan_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if current is None:
        raise AppError("NOT_FOUND")

    vehicle = auth.db.execute(
        select(Vehicle).where(
            Vehicle.tenant_id == auth.tenant_id,
            Vehicle.vehicle_id == current.vehicle_id,
        )
    ).scalar_one_or_none()
    if vehicle is None or not auth.scope.covers_site(vehicle.site_id):
        raise AppError("NOT_FOUND")

    check_version(expected_version, current.row_version)
    if not current.active:
        raise AppError("STATE_TRANSITION_INVALID")
    if body.vehicle_id != current.vehicle_id or body.code != current.code:
        raise AppError("VALIDATION_ERROR")

    current.active = False
    current.suspension_reason = "Remplacé par une nouvelle version"
    auth.db.flush()

    replacement = MaintenancePlan(
        tenant_id=auth.tenant_id,
        vehicle_id=current.vehicle_id,
        code=current.code,
        version=current.version + 1,
        km_interval=body.km_interval,
        hours_interval=body.hours_interval,
        days_interval=body.days_interval,
        active=True,
    )
    auth.db.add(replacement)
    auth.db.flush()
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        site_id=vehicle.site_id,
        action="maintenance.plan.revise",
        entity_type="maintenance_plan",
        entity_id=replacement.maintenance_plan_id,
        before={"previous_plan_id": current.maintenance_plan_id, "version": current.version},
        after={"new_plan_id": replacement.maintenance_plan_id, "version": replacement.version},
        changed_fields=("version", "km_interval", "hours_interval", "days_interval"),
    )
    auth.db.commit()
    return replacement
