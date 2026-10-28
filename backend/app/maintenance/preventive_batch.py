"""Préparer les échéances de plusieurs plans sans effet de bord.

Étape d'automatisation : la persistance et l'ordonnancement sont volontairement
séparés afin de pouvoir contrôler les données de référence avant écriture.
"""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.maintenance.preventive import CurrentMeters, ServiceBaseline, ServiceRule
from app.maintenance.preventive_due_candidates import DueCandidate, due_candidates


@dataclass(frozen=True)
class PlanSnapshot:
    tenant_id: UUID
    plan_id: UUID
    vehicle_id: UUID
    rule: ServiceRule
    baseline: ServiceBaseline
    meters: CurrentMeters
    active: bool = True


@dataclass(frozen=True)
class PlannedDue:
    tenant_id: UUID
    plan_id: UUID
    vehicle_id: UUID
    candidate: DueCandidate


def preview_due_batch(plans: tuple[PlanSnapshot, ...], as_of: date) -> tuple[PlannedDue, ...]:
    """Produire une échéance au plus par plan/cycle, dans un ordre stable.

    Une version suspendue est ignorée. Le moteur existant garde le traitement
    conservateur des compteurs incomplets ou non fiables.
    """
    produced: dict[tuple[UUID, UUID, str], PlannedDue] = {}
    for plan in plans:
        if not plan.active:
            continue
        for candidate in due_candidates(plan.rule, plan.baseline, plan.meters, as_of):
            key = (plan.tenant_id, plan.plan_id, candidate.trigger_key)
            produced[key] = PlannedDue(
                tenant_id=plan.tenant_id,
                plan_id=plan.plan_id,
                vehicle_id=plan.vehicle_id,
                candidate=candidate,
            )
    return tuple(
        produced[key]
        for key in sorted(produced, key=lambda item: (str(item[0]), str(item[1]), item[2]))
    )
