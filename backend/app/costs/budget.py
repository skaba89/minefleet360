"""Budget prévisionnel et analyse des écarts (contrôle de gestion, tranche 1).

Décision du 17 novembre 2026 : granularité site × mois × composante. Le réel est le coût complet
existant (`vehicle_costs`, docs/LIVRAISON_COUT_COMPLET.md) agrégé par site et par composante : aucune
nouvelle méthode de coût. Règles :
- budget : version la plus récente (table en ajout seul, chaque révision conservée et journalisée) ;
- réel : statut le moins favorable des engins du site (complet / estimé / partiel / insuffisant) ; un
  engin sans montant exploitable rend le réel « partiel » (minimum) s'il existe d'autres montants,
  « insuffisant » sinon ;
- écart = réel − budget, seulement si les deux montants existent dans la même devise (aucune conversion) ;
- mois futur : aucun réel ; mois en cours : réel arrêté à maintenant.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.costs.models import CostBudget
from app.costs.service import CENT, SEVERITY, VehicleCost, vehicle_costs
from app.organization.contracts import site_in_scope

ComponentCode = Literal["FUEL", "PARTS", "LABOUR", "TYRES"]
COMPONENTS: tuple[ComponentCode, ...] = ("FUEL", "PARTS", "LABOUR", "TYRES")
_ATTRIBUTE: dict[str, str] = {"FUEL": "fuel", "PARTS": "parts", "LABOUR": "labour", "TYRES": "tyres"}
ActualStatus = Literal["COMPLETE", "ESTIMATED", "PARTIAL", "INSUFFICIENT", "FUTURE"]
MAX_MONTHS = 12


class VarianceRow(BaseModel):
    site_id: uuid.UUID
    month: str  # AAAA-MM
    component: ComponentCode
    budget_amount: Decimal | None
    budget_currency: str | None
    actual_amount: Decimal | None
    actual_currency: str | None
    actual_status: ActualStatus
    # Écart calculé seulement si budget et réel existent dans la même devise ; sinon null + motif.
    variance_amount: Decimal | None
    variance_percent: Decimal | None
    not_comparable_reason: str | None


@dataclass
class _Actual:
    amounts: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    worst: str = "COMPLETE"
    unknown: bool = False  # au moins un engin sans montant exploitable pour cette composante


def month_start(value: str) -> date:
    try:
        year, month = (int(p) for p in value.split("-"))
        return date(year, month, 1)
    except (ValueError, TypeError) as exc:
        raise AppError("VALIDATION_ERROR", details=[{"field": "month", "type": "format"}]) from exc


def _next_month(day: date) -> date:
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1)


def _months(first: date, last: date) -> list[date]:
    if last < first:
        raise AppError("END_BEFORE_START")
    months = [first]
    while months[-1] < last:
        months.append(_next_month(months[-1]))
    if len(months) > MAX_MONTHS:
        raise AppError("VALIDATION_ERROR", details=[{"field": "from", "type": "period_too_long"}])
    return months


def create_budget(
    auth: Authorized,
    *,
    site_id: uuid.UUID,
    budget_month: date,
    component: ComponentCode,
    amount: Decimal,
    currency: str,
    note: str | None,
) -> CostBudget:
    if site_in_scope(auth.db, auth.scope, site_id) is None:
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "site_id"}])
    budget = CostBudget(
        tenant_id=auth.tenant_id,
        site_id=site_id,
        budget_month=budget_month,
        component=component,
        amount=amount,
        currency=currency,
        note=note,
        created_by=auth.user_id,
    )
    auth.db.add(budget)
    auth.db.flush()
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        action="cost.budget.create",
        entity_type="cost_budget",
        entity_id=budget.cost_budget_id,
        site_id=site_id,
        actor_user_id=auth.user_id,
        after={
            "budget_month": budget_month.isoformat(),
            "component": component,
            "amount": str(amount),
            "currency": currency,
        },
    )
    auth.db.commit()
    return budget


def _latest_budgets(
    auth: Authorized, sites: frozenset[uuid.UUID] | None, first: date, last: date
) -> dict[tuple[uuid.UUID, date, str], CostBudget]:
    stmt = (
        select(CostBudget)
        .where(CostBudget.budget_month >= first, CostBudget.budget_month <= last)
        .order_by(CostBudget.created_at.desc(), CostBudget.cost_budget_id.desc())
    )
    if sites is not None:
        stmt = stmt.where(CostBudget.site_id.in_(sites))
    latest: dict[tuple[uuid.UUID, date, str], CostBudget] = {}
    for budget in auth.db.execute(stmt).scalars():
        latest.setdefault((budget.site_id, budget.budget_month, budget.component), budget)
    return latest


def _actuals(rows: list[VehicleCost]) -> dict[tuple[uuid.UUID, str], _Actual]:
    actual: dict[tuple[uuid.UUID, str], _Actual] = defaultdict(_Actual)
    for row in rows:
        for code in COMPONENTS:
            component = getattr(row, _ATTRIBUTE[code])
            acc = actual[(row.site_id, code)]
            if SEVERITY[component.status] > SEVERITY[acc.worst]:
                acc.worst = component.status
            if component.amount is None:
                acc.unknown = True
            elif component.currency is not None:
                acc.amounts[component.currency] += component.amount
    return actual


def _row(
    site_id: uuid.UUID,
    month: date,
    code: ComponentCode,
    budget: CostBudget | None,
    acc: _Actual | None,
    future: bool,
) -> VarianceRow:
    budget_amount = budget.amount if budget else None
    budget_currency = budget.currency if budget else None
    if future:
        actual_amount, actual_currency, status = None, None, "FUTURE"
    elif acc is None or (not acc.amounts and not acc.unknown):
        actual_amount, actual_currency, status = (
            Decimal("0.00"),
            budget_currency,
            "COMPLETE",
        )  # aucune activité
    elif len(acc.amounts) > 1:
        actual_amount, actual_currency, status = None, None, "INSUFFICIENT"
    elif not acc.amounts:
        actual_amount, actual_currency, status = None, None, "INSUFFICIENT"
    else:
        ((actual_currency, total),) = acc.amounts.items()
        actual_amount = total.quantize(CENT)
        status = "PARTIAL" if acc.unknown else acc.worst
    reason = None
    variance = percent = None
    if budget is None:
        reason = "aucun budget saisi"
    elif status == "FUTURE":
        reason = "mois à venir"
    elif actual_amount is None:
        reason = "réel indisponible (données insuffisantes ou devises multiples)"
    elif actual_currency != budget_currency:
        reason = "devises différentes : aucune conversion"
    else:
        variance = (actual_amount - budget.amount).quantize(CENT)
        percent = (variance * 100 / budget.amount).quantize(CENT) if budget.amount else None
    return VarianceRow(
        site_id=site_id,
        month=month.strftime("%Y-%m"),
        component=code,
        budget_amount=budget_amount,
        budget_currency=budget_currency,
        actual_amount=actual_amount,
        actual_currency=actual_currency,
        actual_status=status,
        variance_amount=variance,
        variance_percent=percent,
        not_comparable_reason=reason,
    )


def budget_variance(
    auth: Authorized, *, sites: frozenset[uuid.UUID] | None, first: date, last: date
) -> list[VarianceRow]:
    months = _months(first, last)
    budgets = _latest_budgets(auth, sites, months[0], months[-1])
    now = auth.clock.now()
    result: list[VarianceRow] = []
    for month in months:
        start = datetime(month.year, month.month, 1, tzinfo=UTC)
        future = start >= now
        nxt = _next_month(month)
        rows = (
            []
            if future
            else vehicle_costs(
                auth, start=start, end=min(datetime(nxt.year, nxt.month, 1, tzinfo=UTC), now), site_ids=sites
            )
        )
        actual = _actuals(rows)
        site_ids = {key[0] for key in actual} | {key[0] for key in budgets if key[1] == month}
        for site_id in sorted(site_ids, key=str):
            for code in COMPONENTS:
                result.append(
                    _row(
                        site_id,
                        month,
                        code,
                        budgets.get((site_id, month, code)),
                        actual.get((site_id, code)),
                        future,
                    )
                )
    return result
