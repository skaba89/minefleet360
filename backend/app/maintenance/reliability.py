"""Fiabilité et coûts de maintenance par engin (roadmap P1 n° 10, docs/LIVRAISON_FIABILITE.md).

Définitions (période P = [début, fin), fin bornée à maintenant) :
- Panne : OT CORRECTIF signalé dans P, hors REJECTED/CANCELLED.
- Immobilisation : union, par engin, des intervalles [signalement (panne bloquante) ou début d'intervention,
  clôture ou maintenant], découpée sur P. Les chevauchements ne sont comptés qu'une fois.
- Délai moyen de remise en service (MTTR) : moyenne de (clôture − signalement) des OT correctifs
  clôturés dans P.
- Durée de service d'un engin : P bornée par sa mise en service (début du jour, heure du site) et sa réforme
  (fin du jour). Un engin hors service sur toute la période et sans OT est omis ; s'il a des OT malgré tout
  (dates incohérentes), la durée de P est utilisée et `service_dates_conflict` le signale.
- MTBF : (durée de service − immobilisation) / nombre de pannes ; absent sans panne.
- Disponibilité : (durée de service − immobilisation) / durée de service. L'immobilisation est bornée à la
  durée de service.
- Main-d'œuvre et pièces : celles des OT (correctifs et préventifs) clôturés dans P. Le coût pièces ne somme
  que les sorties valorisées liées à l'OT ; `parts_cost_complete` est faux dès qu'une sortie n'est pas
  valorisée.
Heures de fonctionnement (horamètre, relevés en ajout seul, ordonnés, jamais en baisse hors remise à zéro) :
- Plage mesurée : du premier au dernier relevé HOUR_METER pris dans la durée de service (au moins 2 relevés).
- Heures de fonctionnement : somme des progressions entre relevés consécutifs de la plage ; une remise à zéro
  coupe le segment (sa progression n'est pas comptée). Rien n'est extrapolé hors des relevés.
- Taux d'utilisation : heures de fonctionnement / (plage mesurée − immobilisation sur la plage).
- MTBF en heures de fonctionnement : heures de fonctionnement / pannes signalées sur la plage.
- Couverture : plage mesurée / durée de service. Des heures de fonctionnement supérieures à la plage
  écoulée sont une anomalie de relevés : utilisation non calculée, `meter_anomaly` vrai.
Aucune valeur n'est extrapolée : un engin sans OT a 100 % de disponibilité « selon l'atelier », pas mesurée.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta, tzinfo
from decimal import Decimal
from itertools import pairwise
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import func, or_, select

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.errors import AppError
from app.fleet.contracts import VehicleRef, vehicles_in_scope
from app.fleet.models import VehicleMeterReading
from app.maintenance.models import WorkOrder, WorkOrderLabour
from app.maintenance.parts_costs import aggregate_parts_cost
from app.maintenance.parts_models import SparePartMovement
from app.organization.contracts import site_timezone

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
    service_hours: Decimal
    service_dates_conflict: bool
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
    operating_hours: Decimal | None = None
    meter_span_hours: Decimal | None = None
    meter_coverage_percent: Decimal | None = None
    utilization_percent: Decimal | None = None
    mtbf_operating_hours: Decimal | None = None
    meter_anomaly: bool = False


class ReliabilityTotals(BaseModel):
    vehicles: int
    service_hours: Decimal
    failures: int
    downtime_hours: Decimal
    availability_percent: Decimal | None
    mttr_hours: Decimal | None
    mtbf_hours: Decimal | None
    labour_hours: Decimal
    parts_cost_known: Decimal | None
    parts_cost_complete: bool
    metered_vehicles: int = 0
    operating_hours: Decimal | None = None
    utilization_percent: Decimal | None = None
    mtbf_operating_hours: Decimal | None = None


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


def _service_window(
    vehicle: VehicleRef, start: datetime, end: datetime, tz: tzinfo
) -> tuple[datetime, datetime] | None:
    """Intersection de P et de la période de service de l'engin (dates locales du site) ; None si vide."""
    begin, finish = start, end
    if vehicle.commissioned_on is not None:
        begin = max(begin, datetime.combine(vehicle.commissioned_on, time.min, tz))
    if vehicle.decommissioned_on is not None:
        finish = min(finish, datetime.combine(vehicle.decommissioned_on + timedelta(days=1), time.min, tz))
    return (begin, finish) if begin < finish else None


@dataclass(frozen=True)
class _Operating:
    operating: Decimal  # heures moteur
    span: timedelta
    available: timedelta  # plage mesurée − immobilisation sur la plage
    failures: int
    anomaly: bool


def _operating(
    readings: list[VehicleMeterReading],
    window: tuple[datetime, datetime],
    downtime: list[tuple[datetime, datetime]],
    failure_times: list[datetime],
) -> _Operating | None:
    """Heures moteur mesurées par l'horamètre dans la durée de service ; None sans plage mesurée."""
    inside = [r for r in readings if window[0] <= r.read_at <= window[1]]
    if len(inside) < 2 or inside[-1].read_at <= inside[0].read_at:
        return None
    operating = Decimal("0")
    for previous, current in pairwise(inside):
        if current.reset_reason is None:
            operating += max(Decimal(current.value) - Decimal(previous.value), Decimal("0"))
    first, last = inside[0].read_at, inside[-1].read_at
    span = last - first
    on_span = [(max(a, first), min(b, last)) for a, b in downtime if max(a, first) < min(b, last)]
    available = span - _union(on_span)
    failures = sum(1 for moment in failure_times if first <= moment < last)
    anomaly = operating * HOUR > Decimal(span.total_seconds())
    return _Operating(operating, span, available, failures, anomaly)


def _minutes_to_hours(minutes: int) -> Decimal:
    return (Decimal(minutes) / 60).quantize(Decimal("0.01"))


def _ratio(up: Decimal, total: Decimal) -> Decimal | None:
    return (up * 100 / total).quantize(Decimal("0.01")) if total else None


def _percent(up: timedelta, period: timedelta) -> Decimal:
    return (Decimal(up.total_seconds()) * 100 / Decimal(period.total_seconds())).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class _OperatingView:
    operating_hours: Decimal | None = None
    meter_span_hours: Decimal | None = None
    meter_coverage_percent: Decimal | None = None
    utilization_percent: Decimal | None = None
    mtbf_operating_hours: Decimal | None = None
    meter_anomaly: bool = False


def _operating_view(measured: _Operating | None, service: timedelta) -> _OperatingView:
    if measured is None:
        return _OperatingView()
    usable = not measured.anomaly
    return _OperatingView(
        operating_hours=measured.operating.quantize(Decimal("0.01")),
        meter_span_hours=_hours(measured.span),
        meter_coverage_percent=_percent(measured.span, service),
        utilization_percent=_ratio(measured.operating, _hours(measured.available)) if usable else None,
        mtbf_operating_hours=(measured.operating / measured.failures).quantize(Decimal("0.01"))
        if usable and measured.failures
        else None,
        meter_anomaly=measured.anomaly,
    )


@dataclass(frozen=True)
class _OperatingTotals:
    metered_vehicles: int
    operating_hours: Decimal | None = None
    utilization_percent: Decimal | None = None
    mtbf_operating_hours: Decimal | None = None


def _operating_totals(metered: list[_Operating]) -> _OperatingTotals:
    usable = [m for m in metered if not m.anomaly]
    if not usable:
        return _OperatingTotals(metered_vehicles=len(metered))
    operating = sum((m.operating for m in usable), Decimal("0"))
    available = sum((_hours(m.available) for m in usable), Decimal("0"))
    failures = sum(m.failures for m in usable)
    return _OperatingTotals(
        metered_vehicles=len(metered),
        operating_hours=operating.quantize(Decimal("0.01")),
        utilization_percent=_ratio(operating, available),
        mtbf_operating_hours=(operating / failures).quantize(Decimal("0.01")) if failures else None,
    )


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
    meters: dict[uuid.UUID, list[VehicleMeterReading]] = defaultdict(list)
    for reading in (
        db.execute(
            select(VehicleMeterReading)
            .where(
                VehicleMeterReading.vehicle_id.in_([v.vehicle_id for v in vehicles]),
                VehicleMeterReading.meter_kind == "HOUR_METER",
                VehicleMeterReading.read_at >= start,
                VehicleMeterReading.read_at <= end,
            )
            .order_by(VehicleMeterReading.read_at, VehicleMeterReading.recorded_at)
        )
        .scalars()
        .all()
    ):
        meters[reading.vehicle_id].append(reading)
    closed_set = set(closed_in_period)
    metered: list[_Operating] = []
    rows: list[VehicleReliability] = []
    all_repairs: list[timedelta] = []
    total_cost: list[Decimal | None] = []
    zones: dict[uuid.UUID, tzinfo] = {}
    for vehicle in vehicles:
        own = by_vehicle.get(vehicle.vehicle_id, [])
        if vehicle.status == "RETIRED" and not own:
            continue
        if vehicle.site_id not in zones:
            zones[vehicle.site_id] = site_timezone(db, vehicle.site_id)
        window = _service_window(vehicle, start, end, zones[vehicle.site_id])
        conflict = False
        if window is None:
            if not own:
                continue  # hors service sur toute la période : ni disponible ni indisponible
            window, conflict = (start, end), True
        service = window[1] - window[0]
        intervals = []
        for o in own:
            begin = o.reported_at if o.immobilize else o.started_at
            if begin is None:
                continue
            clipped = (max(begin, window[0]), min(o.closed_at or end, window[1]))
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
        measured = _operating(
            meters.get(vehicle.vehicle_id, []),
            window,
            intervals,
            [o.reported_at for o in corrective if start <= o.reported_at < end],
        )
        if measured is not None:
            metered.append(measured)
        view = _operating_view(measured, service)
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
                service_hours=_hours(service),
                service_dates_conflict=conflict,
                failures=failures,
                closed_corrective=len(repairs),
                open_work_orders=sum(1 for o in own if o.closed_at is None),
                downtime_hours=_hours(downtime),
                availability_percent=_percent(service - downtime, service),
                mttr_hours=_hours(sum(repairs, timedelta()) / len(repairs)) if repairs else None,
                mtbf_hours=_hours((service - downtime) / failures) if failures else None,
                labour_hours=_minutes_to_hours(sum(int(labour.get(wo) or 0) for wo in closed)),
                parts_cost_known=parts.known_total if parts else None,
                parts_cost_complete=parts.complete if parts else False,
                operating_hours=view.operating_hours,
                meter_span_hours=view.meter_span_hours,
                meter_coverage_percent=view.meter_coverage_percent,
                utilization_percent=view.utilization_percent,
                mtbf_operating_hours=view.mtbf_operating_hours,
                meter_anomaly=view.meter_anomaly,
            )
        )
    rows.sort(key=lambda r: (r.availability_percent, r.fleet_number))
    failures_total = sum(r.failures for r in rows)
    downtime_total = sum((r.downtime_hours for r in rows), Decimal("0"))
    fleet_hours = sum((r.service_hours for r in rows), Decimal("0"))
    parts_total = aggregate_parts_cost(total_cost) if len(currencies) <= 1 else None
    fleet_operating = _operating_totals(metered)
    return ReliabilityOut(
        period_start=start,
        period_end=end,
        period_hours=_hours(period),
        currency=currency,
        totals=ReliabilityTotals(
            vehicles=len(rows),
            service_hours=fleet_hours,
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
            metered_vehicles=fleet_operating.metered_vehicles,
            operating_hours=fleet_operating.operating_hours,
            utilization_percent=fleet_operating.utilization_percent,
            mtbf_operating_hours=fleet_operating.mtbf_operating_hours,
        ),
        vehicles=rows,
    )
