import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.http import Page, Pagination
from app.fuel import service
from app.fuel.consumption import vehicle_consumption
from app.fuel.schemas import (
    DecisionCreate,
    FuelConsumptionOut,
    FuelIssueOut,
    FuelReceiptOut,
    FuelStocktakeOut,
    IssueCreate,
    MeterKind,
    ReceiptCreate,
    StocktakeCreate,
    TankCreate,
    TankOut,
    ThresholdUpdate,
)

router = APIRouter(tags=["carburant"], route_class=SecuredRoute)
StockRead = Annotated[Authorized, Depends(Require("fuel.stock.read"))]
StockManage = Annotated[Authorized, Depends(Require("fuel.stock.manage"))]
StockReceive = Annotated[Authorized, Depends(Require("fuel.stock.receive"))]
IssueRequest = Annotated[Authorized, Depends(Require("fuel.issue.request"))]
IssueDecide = Annotated[Authorized, Depends(Require("fuel.issue.decide"))]
StocktakeRead = Annotated[Authorized, Depends(Require("fuel.stock.read"))]
StocktakeRecord = Annotated[Authorized, Depends(Require("fuel.stocktake.record"))]
ThresholdManage = Annotated[Authorized, Depends(Require("fuel.stock.threshold"))]


@router.get("/fuel/tanks", response_model=Page[TankOut])
def list_tanks(auth: StockRead, page: Pagination, site_id: uuid.UUID | None = None) -> Page[TankOut]:
    items, total = service.list_tanks(auth, page, site_id=site_id)
    return Page(items=items, page=page.page, page_size=page.page_size, total=total)


@router.post("/fuel/tanks", response_model=TankOut, status_code=status.HTTP_201_CREATED)
def create_tank(body: TankCreate, auth: StockManage) -> TankOut:
    tank = service.create_tank(auth, body)
    return TankOut.model_validate(service.tank_output(auth, tank))


@router.post("/fuel/tanks/{fuel_tank_id}/threshold", response_model=TankOut)
def update_low_stock_threshold(
    fuel_tank_id: uuid.UUID, body: ThresholdUpdate, auth: ThresholdManage
) -> TankOut:
    tank = service.update_threshold(auth, fuel_tank_id, body)
    return TankOut.model_validate(service.tank_output(auth, tank))


@router.post(
    "/fuel/tanks/{fuel_tank_id}/receipts",
    response_model=FuelReceiptOut,
    status_code=status.HTTP_201_CREATED,
)
def receive_fuel(fuel_tank_id: uuid.UUID, body: ReceiptCreate, auth: StockReceive) -> FuelReceiptOut:
    return FuelReceiptOut.model_validate(service.receive(auth, fuel_tank_id, body), from_attributes=True)


@router.get("/fuel/stocktakes", response_model=Page[FuelStocktakeOut])
def list_stocktakes(
    auth: StocktakeRead, page: Pagination, site_id: uuid.UUID | None = None
) -> Page[FuelStocktakeOut]:
    items, total = service.list_stocktakes(auth, page, site_id=site_id)
    return Page(items=items, page=page.page, page_size=page.page_size, total=total)


@router.post(
    "/fuel/tanks/{fuel_tank_id}/stocktakes",
    response_model=FuelStocktakeOut,
    status_code=status.HTTP_201_CREATED,
)
def record_stocktake(
    fuel_tank_id: uuid.UUID, body: StocktakeCreate, auth: StocktakeRecord
) -> FuelStocktakeOut:
    entry = service.record_stocktake(auth, fuel_tank_id, body)
    return FuelStocktakeOut.model_validate(service.stocktake_output(auth, entry))


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


@router.get("/fuel/vehicles/{vehicle_id}/consumption", response_model=Page[FuelConsumptionOut])
def list_vehicle_consumption(
    vehicle_id: uuid.UUID,
    auth: StockRead,
    page: Pagination,
    meter_kind: MeterKind | None = None,
) -> Page[FuelConsumptionOut]:
    rows, total = vehicle_consumption(auth, vehicle_id, page, meter_kind=meter_kind)
    items = [FuelConsumptionOut.model_validate(row) for row in rows]
    return Page(items=items, page=page.page, page_size=page.page_size, total=total)


@router.post("/fuel/issues", response_model=FuelIssueOut, status_code=status.HTTP_201_CREATED)
def create_issue(body: IssueCreate, auth: IssueRequest) -> FuelIssueOut:
    issue = service.create_issue(auth, body)
    return FuelIssueOut.model_validate(service.issue_output(auth, issue))


@router.post("/fuel/issues/{fuel_issue_id}/decision", response_model=FuelIssueOut)
def decide_issue(fuel_issue_id: uuid.UUID, body: DecisionCreate, auth: IssueDecide) -> FuelIssueOut:
    issue = service.decide_issue(auth, fuel_issue_id, body)
    return FuelIssueOut.model_validate(service.issue_output(auth, issue))
