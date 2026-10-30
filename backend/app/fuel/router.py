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
    FuelPumpMeterReadingOut,
    FuelPumpOut,
    FuelPumpReconciliationOut,
    FuelPurchaseOrderOut,
    FuelPurchaseReceiptOut,
    FuelReceiptOut,
    FuelStockAlertOut,
    FuelStocktakeOut,
    FuelSupplierOut,
    IssueCreate,
    MeterKind,
    PumpAnomalyToleranceUpdate,
    PumpCreate,
    PumpMeterReadingCreate,
    PurchaseCreate,
    PurchaseDecisionCreate,
    PurchaseReceiptCreate,
    ReceiptCreate,
    StocktakeCreate,
    SupplierCreate,
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
AlertAcknowledge = Annotated[Authorized, Depends(Require("fuel.alert.acknowledge"))]
PurchaseRead = Annotated[Authorized, Depends(Require("fuel.purchase.read"))]
SupplierManage = Annotated[Authorized, Depends(Require("fuel.supplier.manage"))]
PurchaseCreateGrant = Annotated[Authorized, Depends(Require("fuel.purchase.create"))]
PurchaseDecide = Annotated[Authorized, Depends(Require("fuel.purchase.decide"))]
PurchaseReceive = Annotated[Authorized, Depends(Require("fuel.purchase.receive"))]
PumpManage = Annotated[Authorized, Depends(Require("fuel.pump.manage"))]
PumpMeterRecord = Annotated[Authorized, Depends(Require("fuel.meter.record"))]


@router.get("/fuel/tanks", response_model=Page[TankOut])
def list_tanks(auth: StockRead, page: Pagination, site_id: uuid.UUID | None = None) -> Page[TankOut]:
    items, total = service.list_tanks(auth, page, site_id=site_id)
    return Page(items=items, page=page.page, page_size=page.page_size, total=total)


@router.post("/fuel/tanks", response_model=TankOut, status_code=status.HTTP_201_CREATED)
def create_tank(body: TankCreate, auth: StockManage) -> TankOut:
    tank = service.create_tank(auth, body)
    return TankOut.model_validate(service.tank_output(auth, tank))


@router.get("/fuel/pumps", response_model=Page[FuelPumpOut])
def list_pumps(auth: StockRead, page: Pagination, site_id: uuid.UUID | None = None) -> Page[FuelPumpOut]:
    items, total = service.list_pumps(auth, page, site_id=site_id)
    return Page(items=items, page=page.page, page_size=page.page_size, total=total)


@router.post("/fuel/pumps", response_model=FuelPumpOut, status_code=status.HTTP_201_CREATED)
def create_pump(body: PumpCreate, auth: PumpManage) -> FuelPumpOut:
    pump = service.create_pump(auth, body)
    return FuelPumpOut.model_validate(service.pump_output(auth, pump))


@router.get(
    "/fuel/pumps/{fuel_pump_id}/meter-readings",
    response_model=Page[FuelPumpMeterReadingOut],
)
def list_pump_meter_readings(
    fuel_pump_id: uuid.UUID, auth: StockRead, page: Pagination
) -> Page[FuelPumpMeterReadingOut]:
    rows, total = service.list_pump_meter_readings(auth, fuel_pump_id, page)
    items = [FuelPumpMeterReadingOut.model_validate(row, from_attributes=True) for row in rows]
    return Page(items=items, page=page.page, page_size=page.page_size, total=total)


@router.get(
    "/fuel/pumps/{fuel_pump_id}/reconciliations",
    response_model=Page[FuelPumpReconciliationOut],
)
def list_pump_reconciliations(
    fuel_pump_id: uuid.UUID,
    auth: StockRead,
    page: Pagination,
) -> Page[FuelPumpReconciliationOut]:
    items, total = service.list_pump_reconciliations(auth, fuel_pump_id, page)
    return Page(items=items, page=page.page, page_size=page.page_size, total=total)


@router.put(
    "/fuel/pumps/{fuel_pump_id}/anomaly-tolerance",
    response_model=FuelPumpOut,
)
def update_pump_anomaly_tolerance(
    fuel_pump_id: uuid.UUID,
    body: PumpAnomalyToleranceUpdate,
    auth: PumpManage,
) -> FuelPumpOut:
    pump = service.update_pump_anomaly_tolerance(auth, fuel_pump_id, body)
    return FuelPumpOut.model_validate(service.pump_output(auth, pump))


@router.post(
    "/fuel/pumps/{fuel_pump_id}/meter-readings",
    response_model=FuelPumpMeterReadingOut,
    status_code=status.HTTP_201_CREATED,
)
def record_pump_meter_reading(
    fuel_pump_id: uuid.UUID,
    body: PumpMeterReadingCreate,
    auth: PumpMeterRecord,
) -> FuelPumpMeterReadingOut:
    reading = service.record_pump_meter_reading(auth, fuel_pump_id, body)
    return FuelPumpMeterReadingOut.model_validate(reading, from_attributes=True)


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


@router.get("/fuel/alerts", response_model=Page[FuelStockAlertOut])
def list_stock_alerts(
    auth: StockRead,
    page: Pagination,
    site_id: uuid.UUID | None = None,
    active_only: bool = True,
) -> Page[FuelStockAlertOut]:
    rows, total = service.list_stock_alerts(auth, page, site_id=site_id, active_only=active_only)
    items = [FuelStockAlertOut.model_validate(row) for row in rows]
    return Page(items=items, page=page.page, page_size=page.page_size, total=total)


@router.post("/fuel/alerts/{fuel_stock_alert_id}/acknowledge", response_model=FuelStockAlertOut)
def acknowledge_stock_alert(fuel_stock_alert_id: uuid.UUID, auth: AlertAcknowledge) -> FuelStockAlertOut:
    alert = service.acknowledge_stock_alert(auth, fuel_stock_alert_id)
    return FuelStockAlertOut.model_validate(service.stock_alert_output(auth, alert))


@router.get("/fuel/suppliers", response_model=Page[FuelSupplierOut])
def list_suppliers(
    auth: PurchaseRead, page: Pagination, site_id: uuid.UUID | None = None
) -> Page[FuelSupplierOut]:
    suppliers, total = service.list_suppliers(auth, page, site_id=site_id)
    items = [FuelSupplierOut.model_validate(item, from_attributes=True) for item in suppliers]
    return Page(items=items, page=page.page, page_size=page.page_size, total=total)


@router.post("/fuel/suppliers", response_model=FuelSupplierOut, status_code=status.HTTP_201_CREATED)
def create_supplier(body: SupplierCreate, auth: SupplierManage) -> FuelSupplierOut:
    return FuelSupplierOut.model_validate(service.create_supplier(auth, body), from_attributes=True)


@router.get("/fuel/purchases", response_model=Page[FuelPurchaseOrderOut])
def list_purchases(
    auth: PurchaseRead,
    page: Pagination,
    site_id: uuid.UUID | None = None,
    purchase_status: Annotated[
        Literal["PENDING_APPROVAL", "REJECTED", "APPROVED", "PARTIALLY_RECEIVED", "RECEIVED"] | None,
        Query(alias="status"),
    ] = None,
) -> Page[FuelPurchaseOrderOut]:
    rows, total = service.list_purchases(auth, page, site_id=site_id, status=purchase_status)
    items = [FuelPurchaseOrderOut.model_validate(row) for row in rows]
    return Page(items=items, page=page.page, page_size=page.page_size, total=total)


@router.post("/fuel/purchases", response_model=FuelPurchaseOrderOut, status_code=status.HTTP_201_CREATED)
def create_purchase(body: PurchaseCreate, auth: PurchaseCreateGrant) -> FuelPurchaseOrderOut:
    purchase = service.create_purchase(auth, body)
    return FuelPurchaseOrderOut.model_validate(service.purchase_output(auth, purchase))


@router.post("/fuel/purchases/{fuel_purchase_order_id}/decision", response_model=FuelPurchaseOrderOut)
def decide_purchase(
    fuel_purchase_order_id: uuid.UUID, body: PurchaseDecisionCreate, auth: PurchaseDecide
) -> FuelPurchaseOrderOut:
    purchase = service.decide_purchase(auth, fuel_purchase_order_id, body)
    return FuelPurchaseOrderOut.model_validate(service.purchase_output(auth, purchase))


@router.post(
    "/fuel/purchases/{fuel_purchase_order_id}/receipts",
    response_model=FuelPurchaseReceiptOut,
    status_code=status.HTTP_201_CREATED,
)
def receive_purchase(
    fuel_purchase_order_id: uuid.UUID, body: PurchaseReceiptCreate, auth: PurchaseReceive
) -> FuelPurchaseReceiptOut:
    receipt = service.receive_purchase(auth, fuel_purchase_order_id, body)
    return FuelPurchaseReceiptOut.model_validate(receipt, from_attributes=True)


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
