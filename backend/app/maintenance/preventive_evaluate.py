"""Évaluer les échéances préventives d'un site (bouton atelier) et lister les échéances enregistrées.

Décision du 3 novembre 2026 (docs/PREVENTIVE_DUES.md) : l'évaluation est déclenchée par le responsable
atelier, sous son nom, dans sa portée. Elle réutilise le calcul de prévisualisation (jalon validé +
relevés) et l'enregistrement idempotent `persist_due` : relancer l'évaluation ne crée jamais de doublon
(contrainte `uq_maintenance_due_idempotence`). Aucun OT n'est créé ici : l'atelier planifie ensuite.
La future tâche quotidienne appellera le même service.
"""

import uuid
from typing import Literal

from sqlalchemy import func, select

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.core.http import Page, PageParams
from app.fleet.models import Vehicle
from app.maintenance.preventive import evaluate_due
from app.maintenance.preventive_batch import preview_due_batch
from app.maintenance.preventive_models import MaintenanceDue, MaintenancePlan
from app.maintenance.preventive_persist import MANAGE_PERMISSION, persist_due
from app.maintenance.preventive_preview_read import load_plan_snapshots
from app.maintenance.preventive_schemas import PreventiveEvaluationOut, SiteDueOut
from app.organization.models import Site

DueStatus = Literal["DUE", "SCHEDULED", "COMPLETED", "CANCELLED"]


def _site_ids(auth: Authorized, site_id: uuid.UUID | None) -> frozenset[uuid.UUID] | None:
    """None = toute la société (portée tenant) ; sinon les sites demandés et couverts."""
    if site_id is not None:
        exists = auth.db.scalar(
            select(Site.site_id).where(Site.tenant_id == auth.tenant_id, Site.site_id == site_id)
        )
        if exists is None or not auth.scope.covers_site(site_id):
            raise AppError("NOT_FOUND")
        return frozenset({site_id})
    return None if auth.scope.tenant_wide else auth.scope.site_ids


def evaluate_site_dues(auth: Authorized, site_id: uuid.UUID | None) -> PreventiveEvaluationOut:
    if auth.scope.permission != MANAGE_PERMISSION:
        raise AppError("PERMISSION_DENIED")
    sites = _site_ids(auth, site_id)
    now = auth.clock.now()
    snapshots = load_plan_snapshots(auth.db, auth.tenant_id, sites, as_of=now)
    statuses = [evaluate_due(s.rule, s.baseline, s.meters, now.date()).status for s in snapshots]
    planned = preview_due_batch(snapshots, now.date())
    created = 0
    # Une seule transaction pour le lot (le contexte RLS est transactionnel) : un échec annule tout le lot,
    # et la relance reste sans risque grâce à l'unicité des échéances.
    for item in planned:
        if persist_due(auth, item.plan_id, item.candidate, commit=False):
            created += 1
    out = PreventiveEvaluationOut(
        plans_evaluated=len(snapshots),
        due_now=len(planned),
        created=created,
        already_recorded=len(planned) - created,
        upcoming=statuses.count("UPCOMING"),
        insufficient_data=statuses.count("INSUFFICIENT_DATA"),
    )
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        site_id=site_id,
        action="maintenance.due.evaluate",
        entity_type="maintenance_due",
        after=out.model_dump(),
    )
    auth.db.commit()
    return out


def list_site_dues(
    auth: Authorized, site_id: uuid.UUID | None, statuses: list[DueStatus], page: PageParams
) -> Page[SiteDueOut]:
    sites = _site_ids(auth, site_id)
    query = (
        select(MaintenanceDue, MaintenancePlan.code, Vehicle.fleet_number, Vehicle.site_id)
        .join(
            MaintenancePlan,
            (MaintenancePlan.tenant_id == MaintenanceDue.tenant_id)
            & (MaintenancePlan.maintenance_plan_id == MaintenanceDue.maintenance_plan_id),
        )
        .join(
            Vehicle,
            (Vehicle.tenant_id == MaintenanceDue.tenant_id)
            & (Vehicle.vehicle_id == MaintenanceDue.vehicle_id),
        )
        .where(MaintenanceDue.tenant_id == auth.tenant_id)
    )
    if sites is not None:
        query = query.where(Vehicle.site_id.in_(sites))
    if statuses:
        query = query.where(MaintenanceDue.status.in_(statuses))
    total = auth.db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = auth.db.execute(
        query.order_by(MaintenanceDue.status, MaintenanceDue.created_at, MaintenanceDue.maintenance_due_id)
        .offset(page.offset)
        .limit(page.page_size)
    ).all()
    items = [
        SiteDueOut(
            maintenance_due_id=due.maintenance_due_id,
            maintenance_plan_id=due.maintenance_plan_id,
            plan_code=code,
            vehicle_id=due.vehicle_id,
            fleet_number=fleet_number,
            site_id=vehicle_site,
            trigger_kind=due.trigger_kind,
            status=due.status,
            due_on=due.due_on,
            due_meter=due.due_meter,
            evaluated_at=due.evaluated_at,
            work_order_id=due.work_order_id,
        )
        for due, code, fleet_number, vehicle_site in rows
    ]
    return Page(items=items, page=page.page, page_size=page.page_size, total=total)
