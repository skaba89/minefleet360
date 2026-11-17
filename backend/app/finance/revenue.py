"""Revenus par contrat et marge sur coût complet par site (contrôle de gestion, tranche 3).

Décision du 17 novembre 2026 : revenu = tarif en vigueur × quantité MESURÉE, jamais estimée.
- TONNE : tonnes nettes des pesées valides des missions rattachées au contrat (pesée non annulée ; saisie
  dégradée seulement si approuvée), tarif en vigueur à la date UTC de la pesée ;
- MISSION : forfait par mission terminée sur la période, tarif en vigueur à la date UTC de fin ;
- HOUR / KM : aucune mesure par mission n'existe encore (compteurs par engin, non par mission) : quantité
  non mesurée, revenu « insuffisant » ; aucune répartition inventée ;
- pas de tarif en vigueur à la date d'un fait mesuré : revenu « partiel » (minimum) ou « insuffisant » ;
- pesée dégradée en attente d'approbation : exclue et signalée (revenu « partiel »).
Marge du site = revenus des contrats − coût complet des engins du site (`vehicle_costs`), seulement dans une
même devise. Les missions terminées sans contrat rendent la marge « partielle » : leur revenu n'est pas connu.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import and_, exists, func, select

from app.authz.dependencies import Authorized
from app.costs.service import CENT, SEVERITY, site_totals, vehicle_costs
from app.dispatch.models import Mission, MissionEvent, WeighingTicket, WeighingTicketDecision
from app.finance.models import ContractTariff
from app.legal.contracts import contract_references

Status = Literal["COMPLETE", "PARTIAL", "INSUFFICIENT"]
TONNE = Decimal("1000")


class ContractRevenue(BaseModel):
    contract_id: uuid.UUID
    contract_reference: str
    site_id: uuid.UUID
    amount: Decimal | None
    currency: str | None
    status: Status
    tonnes: Decimal  # tonnes nettes mesurées valorisées ou non
    missions_completed: int
    missing: list[str]


class SiteMargin(BaseModel):
    site_id: uuid.UUID
    revenue: Decimal | None
    revenue_status: Status
    cost: Decimal | None
    cost_status: str
    currency: str | None
    margin: Decimal | None
    margin_percent: Decimal | None
    missions_without_contract: int
    not_comparable_reason: str | None


@dataclass
class _Acc:
    site_id: uuid.UUID
    amounts: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    tonnes: Decimal = Decimal("0")
    missions: int = 0
    missing: set[str] = field(default_factory=set)
    valued: bool = False

    @property
    def status(self) -> Status:
        if not self.missing:
            return "COMPLETE"
        return "PARTIAL" if self.valued and len(self.amounts) == 1 else "INSUFFICIENT"


def _tariffs(auth: Authorized, contract_ids: set[uuid.UUID]) -> dict[uuid.UUID, list[ContractTariff]]:
    out: dict[uuid.UUID, list[ContractTariff]] = defaultdict(list)
    if not contract_ids:
        return out
    stmt = (
        select(ContractTariff)
        .where(ContractTariff.contract_id.in_(contract_ids))
        .order_by(ContractTariff.valid_from.desc())
    )
    for tariff in auth.db.execute(stmt).scalars():
        out[tariff.contract_id].append(tariff)
    return out


def _in_force(versions: list[ContractTariff], day: date) -> ContractTariff | None:
    return next((t for t in versions if t.valid_from <= day), None)


def _value(acc: _Acc, tariff: ContractTariff | None, basis: str, quantity: Decimal, day: date) -> None:
    if tariff is None:
        acc.missing.add(f"aucun tarif en vigueur le {day.isoformat()}")
    elif tariff.basis != basis:
        acc.missing.add(f"tarif {tariff.basis} : quantité non mesurée par mission")
    else:
        acc.amounts[tariff.currency] += quantity * tariff.unit_price
        acc.valued = True


def _decided(kind: str):  # type: ignore[no-untyped-def]
    return exists().where(
        WeighingTicketDecision.tenant_id == WeighingTicket.tenant_id,
        WeighingTicketDecision.weighing_ticket_id == WeighingTicket.weighing_ticket_id,
        WeighingTicketDecision.decision == kind,
    )


def contract_revenues(
    auth: Authorized, *, start: datetime, end: datetime, sites: frozenset[uuid.UUID] | None
) -> list[ContractRevenue]:
    db = auth.db
    scope = [Mission.contract_id.is_not(None)]
    if sites is not None:
        scope.append(Mission.site_id.in_(sites))
    tickets = db.execute(
        select(
            Mission.contract_id,
            Mission.site_id,
            WeighingTicket.weighed_at,
            WeighingTicket.net_kg,
            and_(WeighingTicket.source == "MANUAL_DEGRADED", ~_decided("APPROVED")).label("pending"),
        )
        .join(WeighingTicket, WeighingTicket.mission_id == Mission.mission_id)
        .where(
            *scope, WeighingTicket.weighed_at >= start, WeighingTicket.weighed_at < end, ~_decided("VOIDED")
        )
    ).all()
    completed = db.execute(
        select(Mission.contract_id, Mission.site_id, func.min(MissionEvent.occurred_at))
        .join(MissionEvent, MissionEvent.mission_id == Mission.mission_id)
        .where(
            *scope,
            MissionEvent.event_type == "COMPLETED",
            MissionEvent.occurred_at >= start,
            MissionEvent.occurred_at < end,
        )
        .group_by(Mission.mission_id, Mission.contract_id, Mission.site_id)
    ).all()
    contract_ids = {r[0] for r in tickets if r[0]} | {r[0] for r in completed if r[0]}
    versions = _tariffs(auth, contract_ids)
    acc: dict[uuid.UUID, _Acc] = {}
    for contract_id, site_id, weighed_at, net_kg, pending in tickets:
        assert contract_id is not None  # filtré par la requête
        a = acc.setdefault(contract_id, _Acc(site_id))
        if pending:
            a.missing.add("pesée dégradée en attente d'approbation (exclue)")
            continue
        tonnes = Decimal(net_kg) / TONNE
        a.tonnes += tonnes
        day = weighed_at.date()
        tariff = _in_force(versions[contract_id], day)
        if tariff is None or tariff.basis in ("TONNE", "HOUR", "KM"):
            _value(a, tariff, "TONNE", tonnes, day)
    for contract_id, site_id, finished_at in completed:
        assert contract_id is not None  # filtré par la requête
        a = acc.setdefault(contract_id, _Acc(site_id))
        a.missions += 1
        day = finished_at.date()
        tariff = _in_force(versions[contract_id], day)
        if tariff is None or tariff.basis == "MISSION":
            _value(a, tariff, "MISSION", Decimal("1"), day)
        elif tariff.basis in ("HOUR", "KM"):
            _value(a, tariff, "MISSION", Decimal("0"), day)  # signale la quantité non mesurée
    references = contract_references(db, set(acc))
    out = []
    for contract_id, a in acc.items():
        single = len(a.amounts) == 1
        if len(a.amounts) > 1:
            a.missing.add("plusieurs devises : aucune conversion")
        currency, amount = next(iter(a.amounts.items())) if single else (None, None)
        out.append(
            ContractRevenue(
                contract_id=contract_id,
                contract_reference=references.get(contract_id, "?"),
                site_id=a.site_id,
                amount=amount.quantize(CENT) if amount is not None else None,
                currency=currency,
                status=a.status,
                tonnes=a.tonnes.quantize(Decimal("0.001")),
                missions_completed=a.missions,
                missing=sorted(a.missing),
            )
        )
    return sorted(out, key=lambda r: (r.amount is None, -(r.amount or 0)))


def _uncontracted(
    auth: Authorized, start: datetime, end: datetime, sites: frozenset[uuid.UUID] | None
) -> dict[uuid.UUID, int]:
    stmt = (
        select(Mission.site_id, func.count(func.distinct(Mission.mission_id)))
        .join(MissionEvent, MissionEvent.mission_id == Mission.mission_id)
        .where(
            Mission.contract_id.is_(None),
            MissionEvent.event_type == "COMPLETED",
            MissionEvent.occurred_at >= start,
            MissionEvent.occurred_at < end,
        )
        .group_by(Mission.site_id)
    )
    if sites is not None:
        stmt = stmt.where(Mission.site_id.in_(sites))
    return {site: int(count) for site, count in auth.db.execute(stmt).all()}


def site_margins(
    auth: Authorized,
    revenues: list[ContractRevenue],
    *,
    start: datetime,
    end: datetime,
    sites: frozenset[uuid.UUID] | None,
) -> list[SiteMargin]:
    costs = {s.site_id: s for s in site_totals(vehicle_costs(auth, start=start, end=end, site_ids=sites))}
    uncontracted = _uncontracted(auth, start, end, sites)
    by_site: dict[uuid.UUID, list[ContractRevenue]] = defaultdict(list)
    for r in revenues:
        by_site[r.site_id].append(r)
    out = []
    for site_id in sorted(set(by_site) | set(costs), key=str):
        items = by_site.get(site_id, [])
        currencies = {r.currency for r in items if r.currency}
        status: Status = max((r.status for r in items), key=lambda s: SEVERITY[s], default="COMPLETE")
        revenue: Decimal | None
        if len(currencies) > 1 or any(r.amount is None for r in items):
            revenue, status = None, "INSUFFICIENT"
            rev_currency = None
        else:
            revenue = sum((r.amount or Decimal("0") for r in items), Decimal("0")).quantize(CENT)
            rev_currency = next(iter(currencies), None)
        cost = costs.get(site_id)
        cost_amount = cost.total if cost else Decimal("0.00")
        cost_currency = cost.currency if cost else None
        cost_status = cost.total_status if cost else "COMPLETE"
        missing_contract = int(uncontracted.get(site_id, 0))
        currency = rev_currency or cost_currency
        margin = percent = None
        reason = None
        if revenue is None:
            reason = "revenu indisponible (tarif manquant, quantité non mesurée ou devises multiples)"
        elif cost_amount is None:
            reason = "coût complet indisponible"
        elif rev_currency and cost_currency and rev_currency != cost_currency:
            reason, currency = "devises différentes : aucune conversion", None
        else:
            margin = (revenue - cost_amount).quantize(CENT)
            percent = (margin * 100 / revenue).quantize(CENT) if revenue else None
            if missing_contract:
                reason = f"{missing_contract} mission(s) terminée(s) sans contrat : revenu non comptabilisé"
        out.append(
            SiteMargin(
                site_id=site_id,
                revenue=revenue,
                revenue_status=status,
                cost=cost_amount,
                cost_status=cost_status,
                currency=currency,
                margin=margin,
                margin_percent=percent,
                missions_without_contract=missing_contract,
                not_comparable_reason=reason,
            )
        )
    return out
