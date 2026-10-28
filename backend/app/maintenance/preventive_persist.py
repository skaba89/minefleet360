"""Enregistrement idempotent des échéances préventives dans PostgreSQL.

Service interne uniquement : aucune génération d'OT ni route publique.
Le contexte RLS est établi par la dépendance Authorized de l'appelant.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.fleet.models import Vehicle
from app.maintenance.preventive_due_candidates import DueCandidate
from app.maintenance.preventive_models import MaintenanceDue, MaintenancePlan

MANAGE_PERMISSION = "maintenance.preventive.manage"


def persist_due(auth: Authorized, plan_id: uuid.UUID, candidate: DueCandidate) -> bool:
    """Insérer au plus une échéance par (tenant, plan, cycle).

    Retourne True si créée, False si déjà présente. L'unicité PostgreSQL
    protège les exécutions concurrentes, y compris sur plusieurs workers.
    """
    if auth.scope.permission != MANAGE_PERMISSION:
        raise AppError("PERMISSION_DENIED")

    plan = auth.db.execute(
        select(MaintenancePlan)
        .where(
            MaintenancePlan.tenant_id == auth.tenant_id,
            MaintenancePlan.maintenance_plan_id == plan_id,
            MaintenancePlan.active.is_(True),
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

    stmt = (
        insert(MaintenanceDue)
        .values(
            tenant_id=auth.tenant_id,
            maintenance_plan_id=plan.maintenance_plan_id,
            vehicle_id=plan.vehicle_id,
            trigger_kind=candidate.trigger_kind,
            trigger_key=candidate.trigger_key,
            due_on=candidate.due_on,
            due_meter=candidate.due_meter,
            status="DUE",
        )
        .on_conflict_do_nothing(
            constraint="uq_maintenance_due_idempotence",
        )
        .returning(MaintenanceDue.maintenance_due_id)
    )
    inserted_id = auth.db.execute(stmt).scalar_one_or_none()
    if inserted_id is None:
        return False

    record(
        auth.db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        site_id=vehicle.site_id,
        action="maintenance.due.create",
        entity_type="maintenance_due",
        entity_id=inserted_id,
        changed_fields=("trigger_kind", "trigger_key", "due_on", "due_meter"),
    )
    auth.db.commit()
    return True
