"""Évaluation quotidienne des échéances préventives d'une société (tâche planifiée, acteur SYSTEM).

Même calcul et même enregistrement idempotent que le bouton « Évaluer les échéances » (preventive_evaluate) :
relancer la tâche, ou la lancer après un clic de l'atelier, ne crée aucun doublon. Aucun OT n'est créé.
Le contexte société (RLS) est posé par l'appelant (commande d'exploitation `minefleet evaluate-preventive`).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.contracts import record
from app.fleet.models import Vehicle
from app.maintenance.preventive import evaluate_due
from app.maintenance.preventive_batch import preview_due_batch
from app.maintenance.preventive_models import MaintenancePlan
from app.maintenance.preventive_persist import insert_due
from app.maintenance.preventive_preview_read import load_plan_snapshots


@dataclass
class DailySummary:
    plans_evaluated: int = 0
    due_now: int = 0
    created: int = 0
    already_recorded: int = 0
    upcoming: int = 0
    insufficient_data: int = 0


def evaluate_tenant_dues(
    db: Session, tenant_id: uuid.UUID, now: datetime, *, dry_run: bool = False
) -> DailySummary:
    snapshots = load_plan_snapshots(db, tenant_id, None, as_of=now)
    statuses = [evaluate_due(s.rule, s.baseline, s.meters, now.date()).status for s in snapshots]
    planned = preview_due_batch(snapshots, now.date())
    summary = DailySummary(
        plans_evaluated=len(snapshots),
        due_now=len(planned),
        upcoming=statuses.count("UPCOMING"),
        insufficient_data=statuses.count("INSUFFICIENT_DATA"),
    )
    if planned:
        plans = {
            p.maintenance_plan_id: p
            for p in db.scalars(
                select(MaintenancePlan)
                .where(
                    MaintenancePlan.tenant_id == tenant_id,
                    MaintenancePlan.maintenance_plan_id.in_({item.plan_id for item in planned}),
                    MaintenancePlan.active.is_(True),
                )
                .with_for_update()
            )
        }
        sites = dict(
            db.execute(
                select(Vehicle.vehicle_id, Vehicle.site_id).where(
                    Vehicle.tenant_id == tenant_id,
                    Vehicle.vehicle_id.in_({item.vehicle_id for item in planned}),
                )
            ).all()
        )
        for item in planned:
            plan = plans.get(item.plan_id)
            if plan is None or item.vehicle_id not in sites:
                continue  # plan suspendu ou engin retiré entre la lecture et l'écriture
            if dry_run:
                continue
            if insert_due(
                db,
                tenant_id=tenant_id,
                plan=plan,
                site_id=sites[item.vehicle_id],
                candidate=item.candidate,
                actor_user_id=None,
            ):
                summary.created += 1
        summary.already_recorded = 0 if dry_run else summary.due_now - summary.created
    if not dry_run:
        record(
            db,
            tenant_id=tenant_id,
            actor_kind="SYSTEM",
            action="maintenance.due.evaluate",
            entity_type="maintenance_due",
            after=vars(summary),
        )
    return summary
