import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import select

from app.audit.contracts import record
from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.errors import AppError
from app.core.http import StrictModel
from app.costs.budget import ComponentCode, VarianceRow, budget_variance, create_budget
from app.costs.budget import month_start as parse_month
from app.costs.models import LabourRate
from app.costs.service import SiteCost, VehicleCost, site_totals, vehicle_costs
from app.organization.contracts import active_site_in_scope

router = APIRouter(tags=["coûts"], route_class=SecuredRoute)
Read = Annotated[Authorized, Depends(Require("cost.vehicle.read"))]
RateManage = Annotated[Authorized, Depends(Require("cost.labour_rate.manage"))]
BudgetManage = Annotated[Authorized, Depends(Require("cost.budget.manage"))]
BudgetRead = Annotated[Authorized, Depends(Require("cost.budget.read"))]
MAX_PERIOD = timedelta(days=366)


class VehicleCostsOut(BaseModel):
    period_start: datetime
    period_end: datetime
    vehicles: list[VehicleCost]
    sites: list[SiteCost]


class MonthCost(BaseModel):
    month: str
    cost: VehicleCost | None


class VehicleHistoryOut(BaseModel):
    vehicle_id: uuid.UUID
    months: list[MonthCost]


class LabourRateIn(StrictModel):
    site_id: uuid.UUID | None = None
    hourly_rate: Decimal = Field(gt=0, le=Decimal("1e12"), decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    valid_from: date


class LabourRateOut(BaseModel):
    maintenance_labour_rate_id: uuid.UUID
    site_id: uuid.UUID | None
    hourly_rate: Decimal
    currency: str
    valid_from: date
    created_at: datetime


def _sites(auth: Authorized, site_id: uuid.UUID | None) -> frozenset[uuid.UUID] | None:
    if site_id is not None:
        if not auth.scope.covers_site(site_id):
            raise AppError("NOT_FOUND")
        return frozenset({site_id})
    return None if auth.scope.tenant_wide else frozenset(auth.scope.site_ids)


@router.get("/costs/vehicles", response_model=VehicleCostsOut)
def list_vehicle_costs(
    auth: Read,
    site_id: uuid.UUID | None = None,
    period_start: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    period_end: Annotated[AwareDatetime | None, Query(alias="to")] = None,
) -> VehicleCostsOut:
    now = auth.clock.now()
    end = min(period_end or now, now)
    start = period_start or end - timedelta(days=30)
    if start >= end:
        raise AppError("END_BEFORE_START")
    if end - start > MAX_PERIOD:
        raise AppError("VALIDATION_ERROR", details=[{"field": "from", "type": "period_too_long"}])
    rows = vehicle_costs(auth, start=start, end=end, site_ids=_sites(auth, site_id))
    return VehicleCostsOut(period_start=start, period_end=end, vehicles=rows, sites=site_totals(rows))


@router.get("/costs/vehicles/{vehicle_id}/history", response_model=VehicleHistoryOut)
def vehicle_cost_history(
    vehicle_id: uuid.UUID, auth: Read, months: Annotated[int, Query(ge=1, le=24)] = 6
) -> VehicleHistoryOut:
    """Évolution mensuelle (mois civils UTC) ; le mois en cours s'arrête à maintenant."""
    sites = _sites(auth, None)
    now = auth.clock.now()
    first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    bounds = []
    cursor = first
    for _ in range(months):
        bounds.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    result: list[MonthCost] = []
    found = False
    for month_start in reversed(bounds):
        month_end = (month_start + timedelta(days=32)).replace(day=1)
        rows = vehicle_costs(
            auth, start=month_start, end=min(month_end, now), site_ids=sites, vehicle_id=vehicle_id
        )
        found = found or bool(rows)
        result.append(MonthCost(month=month_start.strftime("%Y-%m"), cost=rows[0] if rows else None))
    if not found:
        raise AppError("NOT_FOUND")
    return VehicleHistoryOut(vehicle_id=vehicle_id, months=result)


@router.get("/costs/labour-rates", response_model=list[LabourRateOut])
def list_labour_rates(auth: RateManage) -> list[LabourRateOut]:
    rows = auth.db.execute(
        select(LabourRate).order_by(LabourRate.site_id.nulls_first(), LabourRate.valid_from.desc())
    ).scalars()
    return [
        LabourRateOut.model_validate(r, from_attributes=True)
        for r in rows
        if r.site_id is None or auth.scope.covers_site(r.site_id)
    ]


@router.post("/costs/labour-rates", status_code=status.HTTP_201_CREATED, response_model=LabourRateOut)
def create_labour_rate(body: LabourRateIn, auth: RateManage) -> LabourRateOut:
    if body.site_id is None and not auth.scope.tenant_wide:
        # Le taux société s'applique à tous les sites : réservé à une portée société.
        raise AppError("PERMISSION_DENIED")
    if body.site_id is not None and active_site_in_scope(auth.db, auth.scope, body.site_id) is None:
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "site_id"}])
    rate = LabourRate(tenant_id=auth.tenant_id, created_by=auth.user_id, **body.model_dump())
    auth.db.add(rate)
    auth.db.flush()
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        action="cost.labour_rate.create",
        entity_type="maintenance_labour_rate",
        entity_id=rate.maintenance_labour_rate_id,
        site_id=rate.site_id,
        actor_user_id=auth.user_id,
        after={
            "hourly_rate": str(rate.hourly_rate),
            "currency": rate.currency,
            "valid_from": str(rate.valid_from),
        },
    )
    out = LabourRateOut.model_validate(rate, from_attributes=True)
    auth.db.commit()
    return out


# --- Budget prévisionnel et écarts (contrôle de gestion, tranche 1) ---------------------------------------


class BudgetIn(StrictModel):
    site_id: uuid.UUID
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    component: ComponentCode
    amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    note: str | None = Field(default=None, max_length=500)


class BudgetOut(BaseModel):
    cost_budget_id: uuid.UUID
    site_id: uuid.UUID
    month: str
    component: str
    amount: Decimal
    currency: str
    note: str | None
    created_at: datetime


class BudgetVarianceOut(BaseModel):
    from_month: str
    to_month: str
    rows: list[VarianceRow]


@router.post("/costs/budgets", status_code=status.HTTP_201_CREATED, response_model=BudgetOut)
def create_cost_budget(body: BudgetIn, auth: BudgetManage) -> BudgetOut:
    """Nouvelle version du budget d'un site pour un mois et une composante (la plus récente fait foi)."""
    budget = create_budget(
        auth,
        site_id=body.site_id,
        budget_month=parse_month(body.month),
        component=body.component,
        amount=body.amount,
        currency=body.currency,
        note=body.note,
    )
    return BudgetOut(
        cost_budget_id=budget.cost_budget_id,
        site_id=budget.site_id,
        month=budget.budget_month.strftime("%Y-%m"),
        component=budget.component,
        amount=budget.amount,
        currency=budget.currency,
        note=budget.note,
        created_at=budget.created_at,
    )


@router.get("/costs/budget-variance", response_model=BudgetVarianceOut)
def cost_budget_variance(
    auth: BudgetRead,
    site_id: uuid.UUID | None = None,
    from_month: Annotated[str | None, Query(alias="from", pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
    to_month: Annotated[str | None, Query(alias="to", pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
) -> BudgetVarianceOut:
    """Budget vs coût complet réel par site × mois × composante (12 mois max, défaut : 6 derniers)."""
    today = auth.clock.now().date()
    last = parse_month(to_month) if to_month else today.replace(day=1)
    if from_month:
        first = parse_month(from_month)
    else:
        first = last
        for _ in range(5):
            first = (first - timedelta(days=1)).replace(day=1)
    rows = budget_variance(auth, sites=_sites(auth, site_id), first=first, last=last)
    return BudgetVarianceOut(from_month=first.strftime("%Y-%m"), to_month=last.strftime("%Y-%m"), rows=rows)
