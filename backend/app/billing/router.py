"""Routes du catalogue de plans SaaS — préfixe /platform/saas-plans (PLATFORM_ADMIN uniquement)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.billing import service
from app.billing.models import SaaSPlan
from app.billing.schemas import PlanCreate, PlanOut, PlanSummary, PlanUpdate
from app.core.http import IfMatch, Page, Pagination, etag

router = APIRouter(prefix="/platform/saas-plans", tags=["plateforme"], route_class=SecuredRoute)


def _plan_summary(plan: SaaSPlan) -> PlanSummary:
    return PlanSummary.model_validate(plan, from_attributes=True)


def _plan_out(plan: SaaSPlan, response: Response) -> PlanOut:
    response.headers["ETag"] = etag(plan.row_version)
    return PlanOut.model_validate(plan, from_attributes=True)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PlanSummary)
def create_plan(
    body: PlanCreate,
    auth: Annotated[Authorized, Depends(Require("billing.plan.create"))],
) -> PlanSummary:
    return _plan_summary(service.create_plan(auth, body))


@router.get("", response_model=Page[PlanSummary])
def list_plans(
    auth: Annotated[Authorized, Depends(Require("billing.plan.list"))], page: Pagination
) -> Page[PlanSummary]:
    items, total = service.list_plans(auth.db, page)
    return Page(
        items=[_plan_summary(plan) for plan in items], page=page.page, page_size=page.page_size, total=total
    )


@router.get("/{plan_id}", response_model=PlanOut)
def get_plan(
    plan_id: uuid.UUID,
    auth: Annotated[Authorized, Depends(Require("billing.plan.list"))],
    response: Response,
) -> PlanOut:
    return _plan_out(service.get_plan(auth.db, plan_id), response)


@router.patch("/{plan_id}", response_model=PlanOut)
def update_plan(
    plan_id: uuid.UUID,
    body: PlanUpdate,
    auth: Annotated[Authorized, Depends(Require("billing.plan.update"))],
    version: IfMatch,
    response: Response,
) -> PlanOut:
    return _plan_out(service.update_plan(auth, plan_id, body, version), response)
