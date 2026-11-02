"""Fiabilité et coûts de maintenance par engin (roadmap P1 n° 10, docs/LIVRAISON_FIABILITE.md).

Définitions (période P = [début, fin), fin bornée à maintenant) :
- Panne : OT CORRECTIF signalé dans P, hors REJECTED/CANCELLED.
- Immobilisation : union, par engin, des intervalles [signalement (panne bloquante) ou début d'intervention,
  clôture ou maintenant], découpée sur P. Les chevauchements ne sont comptés qu'une fois.
- Délai moyen de remise en service (MTTR) : moyenne de (clôture − signalement) des OT correctifs
  clôturés dans P.
- MTBF : (durée de P − immobilisation) / nombre de pannes ; absent sans panne.
- Disponibilité : (durée de P − immobilisation) / durée de P.
- Main-d'œuvre et pièces : celles des OT (correctifs et préventifs) clôturés dans P. Le coût pièces ne somme
  que les sorties valorisées liées à l'OT ; `parts_cost_complete` est faux dès qu'une sortie n'est pas
  valorisée.
Aucune valeur n'est extrapolée : un engin sans OT a 100 % de disponibilité « selon l'atelier », pas mesurée.
"""

import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import func, or_, select

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.errors import AppError
from app.fleet.contracts import vehicles_in_scope
from app.maintenance.models import WorkOrder, WorkOrderLabour
from app.maintenance.parts_costs import aggregate_parts_cost
from app.maintenance.parts_models import SparePartMovement

router = APIRouter(tags=["maintenance"], route_class=SecuredRoute)
Read = Annotated[Authorized, Depends(Require("maintenance.reliability.read"))]
EXCLUDED = ("REJECTED", "CANCELLED")
MAX_PERIOD = timedelta(days=366)
HOUR = Decimal(3600)


class VehicleReliability(BaseModel):
    vehicle_id: uuid.UUID
    fleet_number: str
    site_id: uuid.UUID
    vehicle_status: str
    failures: int
    closed_corrective: int
    open_work_orders: int
    downtime_hours: Decimal
    availability_percent: Decimal
    mttr_hours: Decimal | None
    mtbf_hours: Decimal | None
    labour_hours: Decimal
    parts_cost_known: Decimal | None
    parts_cost_complete: bool


class ReliabilityTotals(BaseModel):
    vehicles: int
    failures: int
    downtime_hours: Decimal
    availability_percent: Decimal | None
    mttr_hours: Decimal | None
    mtbf_hours: Decimal | None
    labour_hours: Decimal
    parts_cost_known: Decimal | None
    parts_cost_complete: bool


class ReliabilityOut(BaseModel):
    period_start: datetime
    period_end: datetime
    period_hours: Decimal
    currency: str | None
    totals: ReliabilityTotals
    vehicles: list[VehicleReliability]


def _hours(delta: timedelta) -> Decimal:
    return (Decimal(delta.total_seconds()) / HOUR).quantize(Decimal("0.01"))


def _union(intervals: list[tuple[datetime, datetime]]) -> timedelta:
    total = timedelta()
    current: tuple[datetime, datetime] | None = None
    for start, end in sorted(intervals):
        if current is None or start > current[1]:
            if current is not None:
                total += current[1] - current[0]
            current = (start, end)
        else:
            current = (current[0], max(current[1], end))
    if current is not None:
        total += current[1] - current[0]
    return total


def _minutes_to_hours(minutes: int) -> Decimal:
    return (Decimal(minutes) / 60).quantize(Decimal("0.01"))


def _ratio(up: Decimal, total: Decimal) -> Decimal | None:
    return (up * 100 / total).quantize(Decimal("0.01")) if total else None


def _percent(up: timedelta, period: timedelta) -> Decimal:
    return (Decimal(up.total_seconds()) * 100 / Decimal(period.total_seconds())).quantize(Decimal("0.01"))


@router.get("/maintenance/reliability", response_model=ReliabilityOut)
def reliability(
    auth: Read,
    site_id: uuid.UUID | None = None,
    period_start: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    period_end: Annotated[AwareDatetime | None, Query(alias="to")] = None,
) -> ReliabilityOut:
    if site_id is not None and not auth.scope.covers_site(site_id):
        raise AppError("NOT_FOUND")
    now = auth.clock.now()
    end = min(period_end or now, now)
    start = period_start or end - timedelta(days=90)
    if start >= end:
        raise AppError("END_BEFORE_START")
    if end - start > MAX_PERIOD:
        raise AppError("VALIDATION_ERROR", details=[{"field": "from", "type": "period_too_long"}])
    period = end - start
    db = auth.db
    sites = None if auth.scope.tenant_wide else auth.scope.site_ids
    if site_id is not None:
        sites = frozenset({site_id})
    scope = [] if sites is None else [WorkOrder.site_id.in_(sites)]

    # OT utiles à la période : ouverts pendant P (signalés avant la fin, non clos avant le début).
    orders = (
        db.execute(
            select(WorkOrder).where(
                *scope,
                WorkOrder.status.not_in(EXCLUDED),
                WorkOrder.reported_at < end,
                or_(WorkOrder.closed_at.is_(None), WorkOrder.closed_at >= start),
            )
        )
        .scalars()
        .all()
    )
    by_vehicle: dict[uuid.UUID, list[WorkOrder]] = defaultdict(list)
    for order in orders:
        by_vehicle[order.vehicle_id].append(order)
    closed_in_period = [
        o.work_order_id for o in orders if o.closed_at is not None and start <= o.closed_at < end
    ]
    labour = dict(
        db.execute(
            select(WorkOrderLabour.work_order_id, func.sum(WorkOrderLabour.minutes))
            .where(WorkOrderLabour.work_order_id.in_(closed_in_period))
            .group_by(WorkOrderLabour.work_order_id)
        ).all()
    )
    issues: dict[uuid.UUID, list[tuple[Decimal | None, str | None]]] = defaultdict(list)
    movement = SparePartMovement
    for work_order_id, cost, currency in db.execute(
        select(movement.work_order_id, movement.total_cost, movement.valuation_currency).where(
            movement.work_order_id.in_(closed_in_period), movement.movement_type == "ISSUE"
        )
    ).all():
        if work_order_id is not None:
            issues[work_order_id].append((cost, currency))
    currencies = {c for rows in issues.values() for amount, c in rows if amount is not None and c is not None}
    currency = next(iter(currencies)) if len(currencies) == 1 else None

    vehicles = vehicles_in_scope(db, sites)
    known = {v.vehicle_id for v in vehicles}
    extra = set(by_vehicle) - known
    if extra:
        vehicles += vehicles_in_scope(db, sites, vehicle_ids=extra, include_retired=True)
    closed_set = set(closed_in_period)
    rows: list[VehicleReliability] = []
    all_repairs: list[timedelta] = []
    total_cost: list[Decimal | None] = []
    for vehicle in vehicles:
        own = by_vehicle.get(vehicle.vehicle_id, [])
        if vehicle.status == "RETIRED" and not own:
            continue
        intervals = []
        for o in own:
            begin = o.reported_at if o.immobilize else o.started_at
            if begin is None:
                continue
            clipped = (max(begin, start), min(o.closed_at or end, end))
            if clipped[0] < clipped[1]:
                intervals.append(clipped)
        downtime = _union(intervals)
        corrective = [o for o in own if o.kind == "CORRECTIVE"]
        failures = sum(1 for o in corrective if start <= o.reported_at < end)
        repairs = [
            o.closed_at - o.reported_at
            for o in corrective
            if o.closed_at is not None and start <= o.closed_at < end
        ]
        all_repairs += repairs
        closed = [o.work_order_id for o in own if o.work_order_id in closed_set]
        costs = [amount for wo in closed for amount, _ in issues.get(wo, [])]
        total_cost += costs
        parts = aggregate_parts_cost(costs) if len(currencies) <= 1 else None
        rows.append(
            VehicleReliability(
                vehicle_id=vehicle.vehicle_id,
                fleet_number=vehicle.fleet_number,
                site_id=vehicle.site_id,
                vehicle_status=vehicle.status,
                failures=failures,
                closed_corrective=len(repairs),
                open_work_orders=sum(1 for o in own if o.closed_at is None),
                downtime_hours=_hours(downtime),
                availability_percent=_percent(period - downtime, period),
                mttr_hours=_hours(sum(repairs, timedelta()) / len(repairs)) if repairs else None,
                mtbf_hours=_hours((period - downtime) / failures) if failures else None,
                labour_hours=_minutes_to_hours(sum(int(labour.get(wo) or 0) for wo in closed)),
                parts_cost_known=parts.known_total if parts else None,
                parts_cost_complete=parts.complete if parts else False,
            )
        )
    rows.sort(key=lambda r: (r.availability_percent, r.fleet_number))
    failures_total = sum(r.failures for r in rows)
    downtime_total = sum((r.downtime_hours for r in rows), Decimal("0"))
    fleet_hours = _hours(period) * len(rows)
    parts_total = aggregate_parts_cost(total_cost) if len(currencies) <= 1 else None
    return ReliabilityOut(
        period_start=start,
        period_end=end,
        period_hours=_hours(period),
        currency=currency,
        totals=ReliabilityTotals(
            vehicles=len(rows),
            failures=failures_total,
            downtime_hours=downtime_total,
            availability_percent=_ratio(fleet_hours - downtime_total, fleet_hours),
            mttr_hours=_hours(sum(all_repairs, timedelta()) / len(all_repairs)) if all_repairs else None,
            mtbf_hours=((fleet_hours - downtime_total) / failures_total).quantize(Decimal("0.01"))
            if failures_total
            else None,
            labour_hours=sum((r.labour_hours for r in rows), Decimal("0")),
            parts_cost_known=parts_total.known_total if parts_total else None,
            parts_cost_complete=parts_total.complete if parts_total else False,
        ),
        vehicles=rows,
    )
