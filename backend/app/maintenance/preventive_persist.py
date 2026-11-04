"""Enregistrement idempotent des échéances préventives dans PostgreSQL.

Service interne uniquement : aucune génération d'OT ni route publique.
Le contexte RLS est établi par la dépendance Authorized de l'appelant.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.fleet.models import Vehicle
from app.maintenance.preventive_due_candidates import DueCandidate
from app.maintenance.preventive_models import MaintenanceDue, MaintenancePlan

MANAGE_PERMISSION = "maintenance.preventive.manage"


def persist_due(
    auth: Authorized, plan_id: uuid.UUID, candidate: DueCandidate, *, commit: bool = True
) -> bool:
    """Insérer au plus une échéance par (tenant, plan, cycle).

    Retourne True si créée, False si déjà présente. L'unicité PostgreSQL
    protège les exécutions concurrentes, y compris sur plusieurs workers.
    `commit=False` : l'appelant (évaluation par lot) valide une seule transaction pour tout le lot.
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

    inserted = insert_due(
        auth.db,
        tenant_id=auth.tenant_id,
        plan=plan,
        site_id=vehicle.site_id,
        candidate=candidate,
        actor_user_id=auth.user_id,
    )
    if not inserted:
        return False
    if commit:
        auth.db.commit()
    return True


def insert_due(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    plan: MaintenancePlan,
    site_id: uuid.UUID,
    candidate: DueCandidate,
    actor_user_id: uuid.UUID | None,
) -> bool:
    """Insertion idempotente d'une échéance et son audit (acteur utilisateur, ou SYSTEM si None).

    Partagée par le bouton « Évaluer les échéances » et la tâche quotidienne : même clé d'unicité
    (`uq_maintenance_due_idempotence`), même audit. La transaction est gérée par l'appelant.
    """
    inserted_id = db.execute(
        insert(MaintenanceDue)
        .values(
            tenant_id=tenant_id,
            maintenance_plan_id=plan.maintenance_plan_id,
            vehicle_id=plan.vehicle_id,
            trigger_kind=candidate.trigger_kind,
            trigger_key=candidate.trigger_key,
            due_on=candidate.due_on,
            due_meter=candidate.due_meter,
            status="DUE",
        )
        .on_conflict_do_nothing(constraint="uq_maintenance_due_idempotence")
        .returning(MaintenanceDue.maintenance_due_id)
    ).scalar_one_or_none()
    if inserted_id is None:
        return False
    record(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_kind="USER" if actor_user_id is not None else "SYSTEM",
        site_id=site_id,
        action="maintenance.due.create",
        entity_type="maintenance_due",
        entity_id=inserted_id,
        changed_fields=("trigger_kind", "trigger_key", "due_on", "due_meter"),
    )
    return True
