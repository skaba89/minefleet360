"""Coût complet d'exploitation par engin (chantier D, docs/LIVRAISON_COUT_COMPLET.md).

Coût complet = carburant + pièces + main-d'œuvre valorisée + pneumatiques. Chaque composante porte un statut :
- COMPLETE : montant entièrement issu de valeurs enregistrées ;
- PARTIAL : une partie des éléments n'est pas valorisée (le montant est un minimum) ;
- ESTIMATED : montant calculé par une méthode d'imputation documentée (carburant, pneus) ;
- INSUFFICIENT : activité constatée mais aucune valeur exploitable (le montant n'est pas fourni).
Aucun chiffre n'est inventé ; les éléments manquants sont listés. Les devises ne sont jamais mélangées sans
conversion : plusieurs devises ⇒ total « INSUFFICIENT ».

Méthodes :
- carburant (ESTIMATED) : litres des sorties APPROUVÉES de la période × prix moyen pondéré des livraisons
  sur commande de la même cuve jusqu'à la fin de la période ; une réception sans commande n'a pas de prix ;
- pièces : sorties valorisées liées aux OT de l'engin, enregistrées dans la période ;
- main-d'œuvre : minutes saisies dans la période × taux horaire en vigueur (site, sinon société) à la date ;
- pneus (ESTIMATED) : km parcourus par chaque pneu sur l'engin dans la période (relevés de compteur des
  événements du pneu) × coût au km du pneu à date (achat + réparations / km mesurés).
Dénominateurs : km et heures = somme des hausses entre relevés de compteur successifs de la période (une
baisse, remplacement de compteur, n'est pas comptée) ; tonnes = pesées valides ; missions terminées.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from itertools import pairwise
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import and_, exists, func, or_, select

from app.authz.dependencies import Authorized
from app.costs.models import LabourRate
from app.dispatch.models import Mission, MissionEvent, WeighingTicket, WeighingTicketDecision
from app.fleet.models import Vehicle, VehicleMeterReading
from app.fuel.models import FuelIssue, FuelIssueDecision, FuelPurchaseOrder, FuelPurchaseReceipt
from app.maintenance.models import WorkOrder, WorkOrderLabour
from app.maintenance.parts_models import SparePartMovement
from app.maintenance.tyre_models import Tyre, TyreEvent
from app.maintenance.tyre_service import usage_from_events

Status = Literal["COMPLETE", "PARTIAL", "ESTIMATED", "INSUFFICIENT"]
CENT = Decimal("0.01")
# Ordre de gravité : le statut d'un total est le moins favorable de ses composantes.
SEVERITY: dict[str, int] = {"COMPLETE": 0, "ESTIMATED": 1, "PARTIAL": 2, "INSUFFICIENT": 3}


class Component(BaseModel):
    amount: Decimal | None
    status: Status
    currency: str | None
    missing: list[str]


class VehicleCost(BaseModel):
    vehicle_id: uuid.UUID
    fleet_number: str
    site_id: uuid.UUID
    fuel: Component
    parts: Component
    labour: Component
    tyres: Component
    total: Decimal | None
    total_status: Status
    currency: str | None
    missing: list[str]
    km: Decimal
    hours: Decimal
    tonnes: Decimal
    missions: int
    cost_per_km: Decimal | None
    cost_per_hour: Decimal | None
    cost_per_tonne: Decimal | None
    cost_per_mission: Decimal | None


class SiteCost(BaseModel):
    site_id: uuid.UUID
    total: Decimal | None
    total_status: Status
    vehicles: int


@dataclass
class _Acc:
    """Accumulateur d'une composante : montants par devise, éléments non valorisés, activité constatée."""

    amounts: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    unvalued: int = 0
    activity: bool = False
    missing: set[str] = field(default_factory=set)

    def component(self, *, estimated: bool = False) -> Component:
        currencies = sorted(self.amounts)
        if len(currencies) > 1:
            return Component(
                amount=None,
                status="INSUFFICIENT",
                currency=None,
                missing=sorted(self.missing | {"devises multiples sans conversion"}),
            )
        if not self.activity:
            return Component(amount=Decimal("0"), status="COMPLETE", currency=None, missing=[])
        if not currencies:
            return Component(amount=None, status="INSUFFICIENT", currency=None, missing=sorted(self.missing))
        amount = self.amounts[currencies[0]].quantize(CENT)
        status: Status = "PARTIAL" if self.unvalued else ("ESTIMATED" if estimated else "COMPLETE")
        return Component(amount=amount, status=status, currency=currencies[0], missing=sorted(self.missing))


def _rising(readings: list[tuple[datetime, Decimal]]) -> Decimal:
    total = Decimal("0")
    ordered = sorted(readings)
    for (_, previous), (_, current) in pairwise(ordered):
        if current > previous:
            total += current - previous
    return total


def _km_on_vehicle(events: list[TyreEvent], vehicle_id: uuid.UUID, start: datetime, end: datetime) -> Decimal:
    """Km parcourus par un pneu sur un engin dans la période, montage par montage (relevés de la période).

    Prudent : la portion d'un montage antérieure au premier relevé de la période n'est pas comptée.
    """
    segments: list[list[tuple[datetime, Decimal]]] = []
    current: list[tuple[datetime, Decimal]] | None = None
    for e in events:
        if e.event_type == "MOUNTED":
            current = [] if e.vehicle_id == vehicle_id else None
        if current is None:
            continue
        if e.event_type in ("MOUNTED", "INSPECTED", "DISMOUNTED") and e.odometer_km is not None:
            if start <= e.occurred_at < end:
                current.append((e.occurred_at, e.odometer_km))
        if e.event_type == "DISMOUNTED":
            segments.append(current)
            current = None
    if current is not None:
        segments.append(current)
    return sum((_rising(segment) for segment in segments), Decimal("0"))


def _ratio(total: Decimal | None, status: Status, quantity: Decimal) -> Decimal | None:
    if total is None or status == "INSUFFICIENT" or quantity <= 0:
        return None
    return (total / quantity).quantize(CENT)


def _fuel_prices(
    auth: Authorized, tank_ids: set[uuid.UUID], end: datetime
) -> dict[uuid.UUID, tuple[Decimal, str] | None]:
    """Prix moyen pondéré par cuve des livraisons sur commande jusqu'à `end` ; None si absent/multidevise."""
    if not tank_ids:
        return {}
    rows = auth.db.execute(
        select(
            FuelPurchaseReceipt.fuel_tank_id,
            FuelPurchaseReceipt.liters,
            FuelPurchaseOrder.unit_price,
            FuelPurchaseOrder.currency,
        )
        .join(
            FuelPurchaseOrder,
            and_(
                FuelPurchaseOrder.tenant_id == FuelPurchaseReceipt.tenant_id,
                FuelPurchaseOrder.fuel_purchase_order_id == FuelPurchaseReceipt.fuel_purchase_order_id,
            ),
        )
        .where(FuelPurchaseReceipt.fuel_tank_id.in_(tank_ids), FuelPurchaseReceipt.occurred_at < end)
    ).all()
    liters: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    value: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    currencies: dict[uuid.UUID, set[str]] = defaultdict(set)
    for tank, qty, price, currency in rows:
        liters[tank] += qty
        value[tank] += qty * price
        currencies[tank].add(currency)
    prices: dict[uuid.UUID, tuple[Decimal, str] | None] = {}
    for tank in tank_ids:
        if liters.get(tank) and len(currencies[tank]) == 1:
            prices[tank] = (value[tank] / liters[tank], next(iter(currencies[tank])))
        else:
            prices[tank] = None
    return prices


def _labour_rate(rates: list[LabourRate], site_id: uuid.UUID, day: date) -> LabourRate | None:
    applicable = [r for r in rates if r.valid_from <= day and r.site_id in (site_id, None)]
    if not applicable:
        return None
    # Le taux du site prime ; à portée égale, le plus récent.
    return max(applicable, key=lambda r: (r.site_id is not None, r.valid_from))


def vehicle_costs(
    auth: Authorized,
    *,
    start: datetime,
    end: datetime,
    site_ids: frozenset[uuid.UUID] | None,
    vehicle_id: uuid.UUID | None = None,
) -> list[VehicleCost]:
    db = auth.db
    vehicle_filter: list[Any] = []
    if site_ids is not None:
        vehicle_filter.append(Vehicle.site_id.in_(site_ids))
    if vehicle_id is not None:
        vehicle_filter.append(Vehicle.vehicle_id == vehicle_id)
    vehicles = db.execute(
        select(Vehicle.vehicle_id, Vehicle.fleet_number, Vehicle.site_id, Vehicle.status).where(
            *vehicle_filter
        )
    ).all()
    ids = {v.vehicle_id for v in vehicles}
    if not ids:
        return []
    fuel: dict[uuid.UUID, _Acc] = defaultdict(_Acc)
    parts: dict[uuid.UUID, _Acc] = defaultdict(_Acc)
    labour: dict[uuid.UUID, _Acc] = defaultdict(_Acc)
    tyres: dict[uuid.UUID, _Acc] = defaultdict(_Acc)

    # Carburant : sorties approuvées de la période, valorisées au prix moyen pondéré de la cuve.
    approved = exists().where(
        FuelIssueDecision.tenant_id == FuelIssue.tenant_id,
        FuelIssueDecision.fuel_issue_id == FuelIssue.fuel_issue_id,
        FuelIssueDecision.decision == "APPROVED",
    )
    issues = db.execute(
        select(FuelIssue.vehicle_id, FuelIssue.fuel_tank_id, FuelIssue.liters).where(
            FuelIssue.vehicle_id.in_(ids),
            FuelIssue.requested_at >= start,
            FuelIssue.requested_at < end,
            approved,
        )
    ).all()
    prices = _fuel_prices(auth, {i.fuel_tank_id for i in issues}, end)
    for issue in issues:
        acc = fuel[issue.vehicle_id]
        acc.activity = True
        price = prices.get(issue.fuel_tank_id)
        if price is None:
            acc.unvalued += 1
            acc.missing.add("prix d'achat du carburant (livraisons sur commande) pour la cuve")
        else:
            acc.amounts[price[1]] += issue.liters * price[0]

    # Pièces : sorties liées aux OT de l'engin, enregistrées dans la période.
    for vid, cost, currency in db.execute(
        select(WorkOrder.vehicle_id, SparePartMovement.total_cost, SparePartMovement.valuation_currency)
        .join(WorkOrder, WorkOrder.work_order_id == SparePartMovement.work_order_id)
        .where(
            WorkOrder.vehicle_id.in_(ids),
            SparePartMovement.movement_type == "ISSUE",
            SparePartMovement.recorded_at >= start,
            SparePartMovement.recorded_at < end,
        )
    ).all():
        acc = parts[vid]
        acc.activity = True
        if cost is None or currency is None:
            acc.unvalued += 1
            acc.missing.add("sorties de pièces non valorisées")
        else:
            acc.amounts[currency] += cost

    # Main-d'œuvre : minutes de la période × taux en vigueur (dates de saisie incluses dans [début, fin)).
    rates = list(db.execute(select(LabourRate)).scalars())
    last_day = end.date() if end.time() != datetime.min.time() else None
    day_filter = (
        WorkOrderLabour.performed_on <= last_day
        if last_day is not None
        else WorkOrderLabour.performed_on < end.date()
    )
    for vid, site_id, minutes, day in db.execute(
        select(WorkOrder.vehicle_id, WorkOrder.site_id, WorkOrderLabour.minutes, WorkOrderLabour.performed_on)
        .join(WorkOrder, WorkOrder.work_order_id == WorkOrderLabour.work_order_id)
        .where(WorkOrder.vehicle_id.in_(ids), WorkOrderLabour.performed_on >= start.date(), day_filter)
    ).all():
        acc = labour[vid]
        acc.activity = True
        rate = _labour_rate(rates, site_id, day)
        if rate is None:
            acc.unvalued += 1
            acc.missing.add("taux horaire de main-d'œuvre")
        else:
            acc.amounts[rate.currency] += Decimal(minutes) / 60 * rate.hourly_rate

    # Pneus : km parcourus sur l'engin dans la période × coût au km du pneu à date.
    tyre_events = (
        db.execute(
            select(TyreEvent)
            .where(
                TyreEvent.tyre_id.in_(select(TyreEvent.tyre_id).where(TyreEvent.vehicle_id.in_(ids))),
                TyreEvent.occurred_at < end,
            )
            .order_by(TyreEvent.occurred_at, TyreEvent.tyre_event_id)
        )
        .scalars()
        .all()
    )
    by_tyre: dict[uuid.UUID, list[TyreEvent]] = defaultdict(list)
    for event in tyre_events:
        by_tyre[event.tyre_id].append(event)
    tyre_rows = (
        {t.tyre_id: t for t in db.execute(select(Tyre).where(Tyre.tyre_id.in_(by_tyre))).scalars()}
        if by_tyre
        else {}
    )
    for tyre_id, events in by_tyre.items():
        tyre = tyre_rows[tyre_id]
        lifetime = usage_from_events(events)
        extra = sum(
            (e.cost for e in events if e.cost is not None and e.event_type in ("REPAIRED", "RETREADED")),
            Decimal("0"),
        )
        for vid in ids:
            km = _km_on_vehicle(events, vid, start, end)
            if km <= 0:
                continue
            acc = tyres[vid]
            acc.activity = True
            if tyre.purchase_cost is None or tyre.currency is None or lifetime.km <= 0:
                acc.unvalued += 1
                acc.missing.add("coût d'achat ou kilométrage mesuré d'un pneu")
            else:
                acc.amounts[tyre.currency] += km * (tyre.purchase_cost + extra) / lifetime.km

    # Dénominateurs.
    meters: dict[tuple[uuid.UUID, str], list[tuple[datetime, Decimal]]] = defaultdict(list)
    for vid, kind, value, read_at in db.execute(
        select(
            VehicleMeterReading.vehicle_id,
            VehicleMeterReading.meter_kind,
            VehicleMeterReading.value,
            VehicleMeterReading.read_at,
        ).where(
            VehicleMeterReading.vehicle_id.in_(ids),
            VehicleMeterReading.read_at >= start,
            VehicleMeterReading.read_at < end,
        )
    ).all():
        meters[(vid, kind)].append((read_at, value))
    voided_or_pending = or_(
        exists().where(
            WeighingTicketDecision.tenant_id == WeighingTicket.tenant_id,
            WeighingTicketDecision.weighing_ticket_id == WeighingTicket.weighing_ticket_id,
            WeighingTicketDecision.decision == "VOIDED",
        ),
        and_(
            WeighingTicket.source == "MANUAL_DEGRADED",
            ~exists().where(
                WeighingTicketDecision.tenant_id == WeighingTicket.tenant_id,
                WeighingTicketDecision.weighing_ticket_id == WeighingTicket.weighing_ticket_id,
                WeighingTicketDecision.decision == "APPROVED",
            ),
        ),
    )
    tonnes = dict(
        db.execute(
            select(WeighingTicket.vehicle_id, func.sum(WeighingTicket.net_kg))
            .where(
                WeighingTicket.vehicle_id.in_(ids),
                WeighingTicket.weighed_at >= start,
                WeighingTicket.weighed_at < end,
                ~voided_or_pending,
            )
            .group_by(WeighingTicket.vehicle_id)
        ).all()
    )
    missions = dict(
        db.execute(
            select(Mission.vehicle_id, func.count(func.distinct(Mission.mission_id)))
            .join(MissionEvent, MissionEvent.mission_id == Mission.mission_id)
            .where(
                Mission.vehicle_id.in_(ids),
                MissionEvent.event_type == "COMPLETED",
                MissionEvent.occurred_at >= start,
                MissionEvent.occurred_at < end,
            )
            .group_by(Mission.vehicle_id)
        ).all()
    )

    out: list[VehicleCost] = []
    for v in vehicles:
        components = {
            "fuel": fuel[v.vehicle_id].component(estimated=True),
            "parts": parts[v.vehicle_id].component(),
            "labour": labour[v.vehicle_id].component(),
            "tyres": tyres[v.vehicle_id].component(estimated=True),
        }
        has_activity = any(acc[v.vehicle_id].activity for acc in (fuel, parts, labour, tyres))
        if v.status == "RETIRED" and not has_activity:
            continue
        currencies = {c.currency for c in components.values() if c.currency}
        missing = sorted({m for c in components.values() for m in c.missing})
        status: Status = max((c.status for c in components.values()), key=lambda s: SEVERITY[s])
        known = [c.amount for c in components.values() if c.amount is not None]
        total: Decimal | None = sum(known, Decimal("0")).quantize(CENT)
        if len(currencies) > 1:
            total, status = None, "INSUFFICIENT"
            missing = sorted({*missing, "devises multiples sans conversion"})
        elif status == "INSUFFICIENT":
            # Une composante sans valeur : le total connu n'est qu'un minimum (ou rien s'il est nul).
            total, status = (total, "PARTIAL") if total else (None, "INSUFFICIENT")
        km = _rising(meters.get((v.vehicle_id, "ODOMETER_KM"), []))
        hours = _rising(meters.get((v.vehicle_id, "HOUR_METER"), []))
        weight = (Decimal(tonnes.get(v.vehicle_id) or 0) / 1000).quantize(Decimal("0.001"))
        count = int(missions.get(v.vehicle_id) or 0)
        out.append(
            VehicleCost(
                vehicle_id=v.vehicle_id,
                fleet_number=v.fleet_number,
                site_id=v.site_id,
                **components,
                total=total,
                total_status=status,
                currency=next(iter(currencies)) if len(currencies) == 1 else None,
                missing=missing,
                km=km,
                hours=hours,
                tonnes=weight,
                missions=count,
                cost_per_km=_ratio(total, status, km),
                cost_per_hour=_ratio(total, status, hours),
                cost_per_tonne=_ratio(total, status, weight),
                cost_per_mission=_ratio(total, status, Decimal(count)),
            )
        )
    out.sort(key=lambda c: (c.total is None, -(c.total or 0), c.fleet_number))
    return out


def site_totals(rows: list[VehicleCost]) -> list[SiteCost]:
    by_site: dict[uuid.UUID, list[VehicleCost]] = defaultdict(list)
    for row in rows:
        by_site[row.site_id].append(row)
    result = []
    for site_id, items in by_site.items():
        currencies = {r.currency for r in items if r.currency}
        status: Status = max((r.total_status for r in items), key=lambda s: SEVERITY[s])
        if len(currencies) > 1:
            total, status = None, "INSUFFICIENT"
        else:
            known = [r.total for r in items if r.total is not None]
            total = sum(known, Decimal("0")).quantize(CENT) if known else None
            if any(r.total is None and r.total_status == "INSUFFICIENT" for r in items) and total is not None:
                status = "PARTIAL"
        result.append(SiteCost(site_id=site_id, total=total, total_status=status, vehicles=len(items)))
    return sorted(result, key=lambda s: (s.total is None, -(s.total or 0)))
