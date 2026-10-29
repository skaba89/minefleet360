import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.http import Page, Pagination
from app.fuel import service
from app.fuel.schemas import (
    DecisionCreate,
    FuelIssueOut,
    FuelReceiptOut,
    IssueCreate,
    ReceiptCreate,
    TankCreate,
    TankOut,
)

router = APIRouter(tags=["carburant"], route_class=SecuredRoute)
StockRead = Annotated[Authorized, Depends(Require("fuel.stock.read"))]
StockManage = Annotated[Authorized, Depends(Require("fuel.stock.manage"))]
StockReceive = Annotated[Authorized, Depends(Require("fuel.stock.receive"))]
IssueRequest = Annotated[Authorized, Depends(Require("fuel.issue.request"))]
IssueDecide = Annotated[Authorized, Depends(Require("fuel.issue.decide"))]


@router.get("/fuel/tanks", response_model=Page[TankOut])
def list_tanks(auth: StockRead, page: Pagination, site_id: uuid.UUID | None = None) -> Page[TankOut]:
    items, total = service.list_tanks(auth, page, site_id=site_id)
    return Page(items=items, page=page.page, page_size=page.page_size, total=total)


@router.post("/fuel/tanks", response_model=TankOut, status_code=status.HTTP_201_CREATED)
def create_tank(body: TankCreate, auth: StockManage) -> TankOut:
    tank = service.create_tank(auth, body)
    return TankOut(
        fuel_tank_id=tank.fuel_tank_id,
        site_id=tank.site_id,
        code=tank.code,
        fuel_type=tank.fuel_type,
        capacity_liters=tank.capacity_liters,
        balance_liters=0,
        reserved_liters=0,
        available_liters=0,
    )


@router.post(
    "/fuel/tanks/{fuel_tank_id}/receipts",
    response_model=FuelReceiptOut,
    status_code=status.HTTP_201_CREATED,
)
def receive_fuel(fuel_tank_id: uuid.UUID, body: ReceiptCreate, auth: StockReceive) -> FuelReceiptOut:
    return FuelReceiptOut.model_validate(service.receive(auth, fuel_tank_id, body), from_attributes=True)


@router.get("/fuel/issues", response_model=Page[FuelIssueOut])
def list_issues(
    auth: StockRead,
    page: Pagination,
    site_id: uuid.UUID | None = None,
    issue_status: Annotated[
        Literal["PENDING_APPROVAL", "APPROVED", "REJECTED"] | None, Query(alias="status")
    ] = None,
) -> Page[FuelIssueOut]:
    items, total = service.list_issues(auth, page, site_id=site_id, status=issue_status)
    return Page(items=items, page=page.page, page_size=page.page_size, total=total)


@router.post("/fuel/issues", response_model=FuelIssueOut, status_code=status.HTTP_201_CREATED)
def create_issue(body: IssueCreate, auth: IssueRequest) -> FuelIssueOut:
    issue = service.create_issue(auth, body)
    return FuelIssueOut.model_validate(service.issue_output(auth, issue))


@router.post("/fuel/issues/{fuel_issue_id}/decision", response_model=FuelIssueOut)
def decide_issue(fuel_issue_id: uuid.UUID, body: DecisionCreate, auth: IssueDecide) -> FuelIssueOut:
    issue = service.decide_issue(auth, fuel_issue_id, body)
    return FuelIssueOut.model_validate(service.issue_output(auth, issue))
