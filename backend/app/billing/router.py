"""Routes SaaS : catalogue de plans (lot 1) et abonnements (lot 2).

- /platform/saas-plans : référentiel plateforme (PLATFORM_ADMIN).
- /platform/tenants/{tenant_id}/subscriptions : cycle de vie de l'abonnement d'une société
  (PLATFORM_ADMIN — le tenant_id du chemin permet la bascule de contexte RLS, pattern
  §6.2 point 4 comme /platform/tenants/{tenant_id}/suspend).
- /tenant/subscription : lecture par la société de SON abonnement et des quotas du plan.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.billing import service
from app.billing.models import SaaSPlan, TenantSubscription
from app.billing.schemas import (
    PlanCreate,
    PlanOut,
    PlanSummary,
    PlanUpdate,
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionRenew,
    SubscriptionStatusChange,
    SubscriptionSummary,
    TenantSubscriptionOut,
)
from app.core.http import IfMatch, Page, Pagination, etag

router = APIRouter(prefix="/platform/saas-plans", tags=["plateforme"], route_class=SecuredRoute)
subscription_router = APIRouter(
    prefix="/platform/tenants/{tenant_id}/subscriptions", tags=["plateforme"], route_class=SecuredRoute
)
own_subscription_router = APIRouter(prefix="/tenant", tags=["tenant"], route_class=SecuredRoute)


def _subscription_summary(db: Session, subscription: TenantSubscription) -> SubscriptionSummary:
    plan = db.get(SaaSPlan, subscription.plan_id)
    return SubscriptionSummary(
        subscription_id=subscription.subscription_id,
        tenant_id=subscription.tenant_id,
        plan_id=subscription.plan_id,
        plan_code=plan.code if plan else "?",
        plan_name=plan.name if plan else "?",
        status=subscription.status,
        trial_ends_at=subscription.trial_ends_at,
        period_ends_at=subscription.period_ends_at,
        suspended_at=subscription.suspended_at,
        cancelled_at=subscription.cancelled_at,
        suspension_reason=subscription.suspension_reason,
        row_version=subscription.row_version,
    )


def _subscription_out(db: Session, subscription: TenantSubscription, response: Response) -> SubscriptionOut:
    response.headers["ETag"] = etag(subscription.row_version)
    return SubscriptionOut(
        **_subscription_summary(db, subscription).model_dump(),
        notes=subscription.notes,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
    )


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


# --- Abonnements (lot 2) ------------------------------------------------------------------------------


@subscription_router.post("", status_code=status.HTTP_201_CREATED, response_model=SubscriptionOut)
def create_subscription(
    tenant_id: uuid.UUID,
    body: SubscriptionCreate,
    auth: Annotated[Authorized, Depends(Require("billing.subscription.manage"))],
    response: Response,
) -> SubscriptionOut:
    return _subscription_out(auth.db, service.create_subscription(auth, tenant_id, body), response)


@subscription_router.get("", response_model=Page[SubscriptionSummary])
def list_subscriptions(
    tenant_id: uuid.UUID,
    auth: Annotated[Authorized, Depends(Require("billing.subscription.manage"))],
    page: Pagination,
    status_filter: Annotated[
        Literal["TRIAL", "ACTIVE", "SUSPENDED", "CANCELLED"] | None, Query(alias="status")
    ] = None,
) -> Page[SubscriptionSummary]:
    items, total = service.list_subscriptions(auth.db, tenant_id, page, status_filter)
    return Page(
        items=[_subscription_summary(auth.db, subscription) for subscription in items],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@subscription_router.post("/{subscription_id}/activate", response_model=SubscriptionOut)
def activate_subscription(
    tenant_id: uuid.UUID,
    subscription_id: uuid.UUID,
    auth: Annotated[Authorized, Depends(Require("billing.subscription.manage"))],
    version: IfMatch,
    response: Response,
) -> SubscriptionOut:
    subscription = service.change_subscription_status(
        auth, tenant_id, subscription_id, version, "ACTIVE", None
    )
    return _subscription_out(auth.db, subscription, response)


@subscription_router.post("/{subscription_id}/suspend", response_model=SubscriptionOut)
def suspend_subscription(
    tenant_id: uuid.UUID,
    subscription_id: uuid.UUID,
    body: SubscriptionStatusChange,
    auth: Annotated[Authorized, Depends(Require("billing.subscription.manage"))],
    version: IfMatch,
    response: Response,
) -> SubscriptionOut:
    subscription = service.change_subscription_status(
        auth, tenant_id, subscription_id, version, "SUSPENDED", body.reason
    )
    return _subscription_out(auth.db, subscription, response)


@subscription_router.post("/{subscription_id}/reactivate", response_model=SubscriptionOut)
def reactivate_subscription(
    tenant_id: uuid.UUID,
    subscription_id: uuid.UUID,
    auth: Annotated[Authorized, Depends(Require("billing.subscription.manage"))],
    version: IfMatch,
    response: Response,
) -> SubscriptionOut:
    subscription = service.change_subscription_status(
        auth, tenant_id, subscription_id, version, "ACTIVE", None
    )
    return _subscription_out(auth.db, subscription, response)


@subscription_router.post("/{subscription_id}/cancel", response_model=SubscriptionOut)
def cancel_subscription(
    tenant_id: uuid.UUID,
    subscription_id: uuid.UUID,
    body: SubscriptionStatusChange,
    auth: Annotated[Authorized, Depends(Require("billing.subscription.manage"))],
    version: IfMatch,
    response: Response,
) -> SubscriptionOut:
    subscription = service.change_subscription_status(
        auth, tenant_id, subscription_id, version, "CANCELLED", body.reason
    )
    return _subscription_out(auth.db, subscription, response)


@subscription_router.post("/{subscription_id}/renew", response_model=SubscriptionOut)
def renew_subscription(
    tenant_id: uuid.UUID,
    subscription_id: uuid.UUID,
    body: SubscriptionRenew,
    auth: Annotated[Authorized, Depends(Require("billing.subscription.manage"))],
    version: IfMatch,
    response: Response,
) -> SubscriptionOut:
    subscription = service.renew_subscription(auth, tenant_id, subscription_id, version, body.period_ends_at)
    return _subscription_out(auth.db, subscription, response)


@own_subscription_router.get("/subscription", response_model=TenantSubscriptionOut)
def read_own_subscription(
    auth: Annotated[Authorized, Depends(Require("billing.subscription.read"))],
    response: Response,
) -> TenantSubscriptionOut:
    subscription = service.read_own_subscription(auth.db, auth.tenant_id)
    response.headers["ETag"] = etag(subscription.row_version)
    plan = auth.db.get(SaaSPlan, subscription.plan_id)
    return TenantSubscriptionOut(
        subscription_id=subscription.subscription_id,
        status=subscription.status,
        trial_ends_at=subscription.trial_ends_at,
        period_ends_at=subscription.period_ends_at,
        plan=PlanSummary.model_validate(plan, from_attributes=True),
    )
