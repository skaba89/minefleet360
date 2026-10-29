"""Assembler une prévisualisation d'échéances depuis des sources vérifiées.

Service interne en lecture seule : aucune échéance ni ordre de travail n'est
persisté. La portée tenant/site est appliquée avant toute hydratation.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fleet.models import Vehicle
from app.maintenance.preventive import CurrentMeters, ServiceBaseline, ServiceRule
from app.maintenance.preventive_baseline_read import load_verified_service_baseline
from app.maintenance.preventive_batch import PlanSnapshot, PlannedDue, preview_due_batch
from app.maintenance.preventive_batch_read import load_active_plans
from app.maintenance.preventive_meter_approval_read import load_approved_current_meters


def _as_utc(as_of: datetime) -> datetime:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of doit inclure un fuseau horaire")
    return as_of.astimezone(timezone.utc)


def _vehicle_sites(
    db: Session,
    tenant_id: uuid.UUID,
    vehicle_ids: frozenset[uuid.UUID],
    site_ids: frozenset[uuid.UUID] | None,
) -> dict[uuid.UUID, uuid.UUID]:
    if not vehicle_ids:
        return {}

    query = select(Vehicle.vehicle_id, Vehicle.site_id).where(
        Vehicle.tenant_id == tenant_id,
        Vehicle.vehicle_id.in_(vehicle_ids),
        Vehicle.status != "RETIRED",
    )
    if site_ids is not None:
        query = query.where(Vehicle.site_id.in_(site_ids))
    return {vehicle_id: site_id for vehicle_id, site_id in db.execute(query)}


def load_plan_snapshots(
    db: Session,
    tenant_id: uuid.UUID,
    site_ids: frozenset[uuid.UUID] | None,
    *,
    as_of: datetime,
) -> tuple[PlanSnapshot, ...]:
    """Hydrater les plans actifs avec preuves d'entretien et cumuls approuvés."""
    as_of_utc = _as_utc(as_of)
    plans = load_active_plans(db, tenant_id, site_ids)
    vehicle_ids = frozenset(plan.vehicle_id for plan in plans)
    vehicle_sites = _vehicle_sites(db, tenant_id, vehicle_ids, site_ids)

    baselines: dict[uuid.UUID, ServiceBaseline] = {}
    meters: dict[uuid.UUID, CurrentMeters] = {}
    snapshots: list[PlanSnapshot] = []

    for plan in plans:
        site_id = vehicle_sites.get(plan.vehicle_id)
        if site_id is None:
            continue

        if plan.vehicle_id not in baselines:
            baselines[plan.vehicle_id] = load_verified_service_baseline(
                db,
                tenant_id,
                plan.vehicle_id,
                as_of=as_of_utc,
            )
            meters[plan.vehicle_id] = load_approved_current_meters(
                db,
                tenant_id,
                plan.vehicle_id,
                site_id,
                as_of=as_of_utc,
            )

        snapshots.append(
            PlanSnapshot(
                tenant_id=tenant_id,
                plan_id=plan.maintenance_plan_id,
                vehicle_id=plan.vehicle_id,
                rule=ServiceRule(
                    km_interval=plan.km_interval,
                    hours_interval=plan.hours_interval,
                    days_interval=plan.days_interval,
                ),
                baseline=baselines[plan.vehicle_id],
                meters=meters[plan.vehicle_id],
                active=True,
            )
        )

    return tuple(snapshots)


def preview_approved_dues(
    db: Session,
    tenant_id: uuid.UUID,
    site_ids: frozenset[uuid.UUID] | None,
    *,
    as_of: datetime,
) -> tuple[PlannedDue, ...]:
    """Prévisualiser les échéances connues sans écriture ni création d'OT."""
    as_of_utc = _as_utc(as_of)
    snapshots = load_plan_snapshots(
        db,
        tenant_id,
        site_ids,
        as_of=as_of_utc,
    )
    return preview_due_batch(snapshots, as_of_utc.date())
