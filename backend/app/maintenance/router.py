import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.http import IfMatch, Page, Pagination, etag
from app.maintenance import preventive_service, service
from app.maintenance.preventive_plan_inputs import PreventivePlanCreate, PreventivePlanSuspend
from app.maintenance.preventive_revise import revise_plan
from app.maintenance.preventive_schedule import schedule_preventive_order
from app.maintenance.preventive_schemas import (
    PreventiveDueOut,
    PreventivePlanOut,
    PreventiveScheduledOrderOut,
)
from app.maintenance.preventive_suspend import suspend_plan
from app.maintenance.preventive_write import create_plan
from app.maintenance.schemas import (
    LabourCreate,
    MechanicOut,
    WorkOrderCreate,
    WorkOrderDecision,
    WorkOrderOut,
    WorkOrderProgress,
    WorkOrderStatus,
)

router = APIRouter(tags=["maintenance"], route_class=SecuredRoute)

WorkOrderRead = Annotated[Authorized, Depends(Require("maintenance.work_order.read"))]
WorkOrderManage = Annotated[Authorized, Depends(Require("maintenance.work_order.manage"))]
WorkOrderExecute = Annotated[Authorized, Depends(Require("maintenance.work_order.execute"))]
PreventiveRead = Annotated[Authorized, Depends(Require("maintenance.preventive.read"))]
PreventiveManage = Annotated[Authorized, Depends(Require("maintenance.preventive.manage"))]


def _tagged(out: WorkOrderOut, response: Response) -> WorkOrderOut:
    response.headers["ETag"] = etag(out.row_version)
    return out


@router.get("/work-orders", response_model=Page[WorkOrderOut], response_model_exclude_unset=True)
def list_work_orders(
    auth: WorkOrderRead,
    page: Pagination,
    site_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    status_filter: Annotated[WorkOrderStatus | None, Query(alias="status")] = None,
    open_only: bool = False,
) -> Page[WorkOrderOut]:
    items, total = service.list_work_orders(
        auth, page, site_id=site_id, vehicle_id=vehicle_id, status=status_filter, open_only=open_only
    )
    return Page(
        items=service.work_orders_out(auth, items), page=page.page, page_size=page.page_size, total=total
    )


@router.get("/work-orders/{work_order_id}", response_model=WorkOrderOut, response_model_exclude_unset=True)
def get_work_order(work_order_id: uuid.UUID, auth: WorkOrderRead, response: Response) -> WorkOrderOut:
    order = service.work_order_in_scope(auth, work_order_id)
    return _tagged(service.work_orders_out(auth, [order], detail=True)[0], response)


@router.post(
    "/work-orders",
    status_code=status.HTTP_201_CREATED,
    response_model=WorkOrderOut,
    response_model_exclude_unset=True,
)
def create_work_order(
    body: WorkOrderCreate,
    auth: Annotated[Authorized, Depends(Require("maintenance.work_order.request"))],
    response: Response,
) -> WorkOrderOut:
    return _tagged(service.create_work_order(auth, body), response)


@router.post(
    "/work-orders/{work_order_id}/decision", response_model=WorkOrderOut, response_model_exclude_unset=True
)
def decide_work_order(
    work_order_id: uuid.UUID,
    body: WorkOrderDecision,
    auth: WorkOrderManage,
    version: IfMatch,
    response: Response,
) -> WorkOrderOut:
    return _tagged(service.decide(auth, work_order_id, body, version), response)


@router.post(
    "/work-orders/{work_order_id}/progress", response_model=WorkOrderOut, response_model_exclude_unset=True
)
def progress_work_order(
    work_order_id: uuid.UUID,
    body: WorkOrderProgress,
    auth: WorkOrderExecute,
    version: IfMatch,
    response: Response,
) -> WorkOrderOut:
    return _tagged(service.progress(auth, work_order_id, body, version), response)


@router.post(
    "/work-orders/{work_order_id}/labour",
    status_code=status.HTTP_201_CREATED,
    response_model=WorkOrderOut,
    response_model_exclude_unset=True,
)
def add_work_order_labour(
    work_order_id: uuid.UUID, body: LabourCreate, auth: WorkOrderExecute, response: Response
) -> WorkOrderOut:
    return _tagged(service.add_labour(auth, work_order_id, body), response)


@router.get("/maintenance-mechanics", response_model=list[MechanicOut])
def list_mechanics(auth: WorkOrderManage, site_id: uuid.UUID | None = None) -> list[MechanicOut]:
    # Mécaniciens assignables sur un site (rôle MECHANIC ou WORKSHOP_CHIEF) ; aucun site → liste vide.
    return service.mechanics(auth, site_id) if site_id is not None else []


@router.get("/vehicles/{vehicle_id}/preventive-plans", response_model=list[PreventivePlanOut])
def list_vehicle_preventive_plans(
    vehicle_id: uuid.UUID, auth: PreventiveRead, active_only: bool = False
) -> list[PreventivePlanOut]:
    return [
        PreventivePlanOut.model_validate(item)
        for item in preventive_service.plans_for_vehicle(auth, vehicle_id, active_only=active_only)
    ]


@router.get("/vehicles/{vehicle_id}/preventive-dues", response_model=list[PreventiveDueOut])
def list_vehicle_preventive_dues(vehicle_id: uuid.UUID, auth: PreventiveRead) -> list[PreventiveDueOut]:
    return [
        PreventiveDueOut.model_validate(item)
        for item in preventive_service.dues_for_vehicle(auth, vehicle_id)
    ]


@router.post(
    "/preventive-plans",
    status_code=status.HTTP_201_CREATED,
    response_model=PreventivePlanOut,
)
def create_preventive_plan(body: PreventivePlanCreate, auth: PreventiveManage) -> PreventivePlanOut:
    return PreventivePlanOut.model_validate(create_plan(auth, body))


@router.post("/preventive-plans/{plan_id}/suspend", response_model=PreventivePlanOut)
def suspend_preventive_plan(
    plan_id: uuid.UUID,
    body: PreventivePlanSuspend,
    auth: PreventiveManage,
    version: IfMatch,
    response: Response,
) -> PreventivePlanOut:
    plan = suspend_plan(auth, plan_id, body, version)
    response.headers["ETag"] = etag(plan.row_version)
    return PreventivePlanOut.model_validate(plan)


@router.post("/preventive-plans/{plan_id}/revise", response_model=PreventivePlanOut)
def revise_preventive_plan(
    plan_id: uuid.UUID,
    body: PreventivePlanCreate,
    auth: PreventiveManage,
    version: IfMatch,
    response: Response,
) -> PreventivePlanOut:
    plan = revise_plan(auth, plan_id, body, version)
    response.headers["ETag"] = etag(plan.row_version)
    return PreventivePlanOut.model_validate(plan)


@router.post(
    "/preventive-dues/{due_id}/schedule",
    status_code=status.HTTP_200_OK,
    response_model=PreventiveScheduledOrderOut,
)
def schedule_preventive_due(due_id: uuid.UUID, auth: PreventiveManage) -> PreventiveScheduledOrderOut:
    """Planifier une échéance éligible ; rejouer retourne le même ordre de travail."""
    return PreventiveScheduledOrderOut(work_order_id=schedule_preventive_order(auth, due_id))
