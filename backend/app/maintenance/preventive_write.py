"""Écriture interne d'un plan préventif, sans exposition HTTP.

Permission d'atelier, portée site et RLS sont vérifiées avant toute écriture.
L'audit et l'insertion appartiennent à la même transaction.
"""

import uuid

from sqlalchemy import select

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.fleet.models import Vehicle
from app.maintenance.preventive_models import MaintenancePlan
from app.maintenance.preventive_plan_inputs import PreventivePlanCreate

MANAGE_PERMISSION = "maintenance.work_order.manage"


def create_plan(auth: Authorized, body: PreventivePlanCreate) -> MaintenancePlan:
    """Créer la première version d'un plan (appel interne depuis une route protégée).

    Le futur endpoint doit déclarer Require(MANAGE_PERMISSION). L'unicité
    (tenant, véhicule, code, version) est aussi imposée par PostgreSQL.
    """
    if auth.scope.permission != MANAGE_PERMISSION:
        raise AppError("PERMISSION_DENIED")

    vehicle = auth.db.execute(
        select(Vehicle)
        .where(Vehicle.tenant_id == auth.tenant_id, Vehicle.vehicle_id == body.vehicle_id)
        .with_for_update()
    ).scalar_one_or_none()
    if vehicle is None or not auth.scope.covers_site(vehicle.site_id):
        raise AppError("NOT_FOUND")

    existing = auth.db.execute(
        select(MaintenancePlan.maintenance_plan_id).where(
            MaintenancePlan.tenant_id == auth.tenant_id,
            MaintenancePlan.vehicle_id == body.vehicle_id,
            MaintenancePlan.code == body.code,
        )
    ).first()
    if existing is not None:
        raise AppError("VERSION_CONFLICT")

    plan = MaintenancePlan(
        tenant_id=auth.tenant_id,
        vehicle_id=body.vehicle_id,
        code=body.code,
        version=1,
        km_interval=body.km_interval,
        hours_interval=body.hours_interval,
        days_interval=body.days_interval,
        active=True,
    )
    auth.db.add(plan)
    auth.db.flush()
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        site_id=vehicle.site_id,
        action="maintenance.plan.create",
        entity_type="maintenance_plan",
        entity_id=plan.maintenance_plan_id,
        changed_fields=("code", "km_interval", "hours_interval", "days_interval"),
    )
    auth.db.commit()
    return plan
