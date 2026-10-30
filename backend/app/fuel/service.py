"""Opérations de stock carburant avec réservations sous verrou de cuve."""

import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.assignment.models import VehicleAssignment
from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.core.http import PageParams
from app.core.tenancy import set_tenant_context
from app.fleet.models import Vehicle, VehicleCategory
from app.fuel.models import (
    FuelIssue,
    FuelIssueDecision,
    FuelPurchaseDecision,
    FuelPurchaseOrder,
    FuelPurchaseReceipt,
    FuelStockAlert,
    FuelStockMovement,
    FuelStocktake,
    FuelSupplier,
    FuelTank,
)
from app.fuel.schemas import (
    DecisionCreate,
    IssueCreate,
    PurchaseCreate,
    PurchaseDecisionCreate,
    PurchaseReceiptCreate,
    ReceiptCreate,
    StocktakeCreate,
    SupplierCreate,
    TankCreate,
    ThresholdUpdate,
)
from app.workforce.models import Driver

Issue = FuelIssue
Decision = FuelIssueDecision
Movement = FuelStockMovement
Tank = FuelTank
StockAlert = FuelStockAlert
Supplier = FuelSupplier
PurchaseOrder = FuelPurchaseOrder
PurchaseDecision = FuelPurchaseDecision
PurchaseReceipt = FuelPurchaseReceipt
ZERO = Decimal("0")


def _audit(auth: Authorized, action: str, entity_id: uuid.UUID, site_id: uuid.UUID) -> None:
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action=action,
        entity_type="fuel",
        entity_id=entity_id,
        site_id=site_id,
    )


def _in_scope(auth: Authorized, site_id: uuid.UUID) -> bool:
    return auth.scope.covers_site(site_id)


def _tank(auth: Authorized, tank_id: uuid.UUID, *, lock: bool = False) -> Tank:
    stmt = select(Tank).where(Tank.tenant_id == auth.tenant_id, Tank.fuel_tank_id == tank_id)
    if lock:
        stmt = stmt.with_for_update()
    tank = auth.db.scalar(stmt)
    if tank is None or not _in_scope(auth, tank.site_id):
        raise AppError("NOT_FOUND")
    return tank


def _balance(db: Session, tenant_id: uuid.UUID, tank_id: uuid.UUID) -> Decimal:
    value = db.scalar(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (
                            Movement.movement_type.in_(("RECEIPT", "STOCKTAKE_IN", "PURCHASE_RECEIPT")),
                            Movement.liters,
                        ),
                        else_=-Movement.liters,
                    )
                ),
                ZERO,
            )
        ).where(Movement.tenant_id == tenant_id, Movement.fuel_tank_id == tank_id)
    )
    return Decimal(value or ZERO)


def _reserved(db: Session, tenant_id: uuid.UUID, tank_id: uuid.UUID) -> Decimal:
    value = db.scalar(
        select(func.coalesce(func.sum(Issue.liters), ZERO))
        .outerjoin(
            Decision,
            (Decision.tenant_id == Issue.tenant_id) & (Decision.fuel_issue_id == Issue.fuel_issue_id),
        )
        .where(
            Issue.tenant_id == tenant_id,
            Issue.fuel_tank_id == tank_id,
            Decision.fuel_issue_decision_id.is_(None),
        )
    )
    return Decimal(value or ZERO)


def _sync_low_stock_alert(auth: Authorized, tank: Tank) -> None:
    """Ouvre ou clôt le cycle d'alerte sous le même verrou que la cuve."""
    balance = _balance(auth.db, auth.tenant_id, tank.fuel_tank_id)
    active = auth.db.scalar(
        select(StockAlert)
        .where(
            StockAlert.tenant_id == auth.tenant_id,
            StockAlert.fuel_tank_id == tank.fuel_tank_id,
            StockAlert.resolved_at.is_(None),
        )
        .with_for_update()
    )
    threshold = tank.low_stock_threshold_liters
    if threshold is not None and balance <= threshold:
        if active is None:
            alert = StockAlert(
                tenant_id=auth.tenant_id,
                site_id=tank.site_id,
                fuel_tank_id=tank.fuel_tank_id,
                threshold_liters=threshold,
                balance_liters=balance,
            )
            auth.db.add(alert)
            auth.db.flush()
            _audit(auth, "fuel.stock.alert.trigger", alert.fuel_stock_alert_id, tank.site_id)
        return
    if active is not None:
        active.resolved_at = auth.clock.now()
        active.resolution_balance_liters = balance
        auth.db.flush()
        _audit(auth, "fuel.stock.alert.resolve", active.fuel_stock_alert_id, tank.site_id)


def tank_output(auth: Authorized, tank: Tank) -> dict[str, object]:
    balance = _balance(auth.db, auth.tenant_id, tank.fuel_tank_id)
    reserved = _reserved(auth.db, auth.tenant_id, tank.fuel_tank_id)
    threshold = tank.low_stock_threshold_liters
    return {
        "fuel_tank_id": tank.fuel_tank_id,
        "site_id": tank.site_id,
        "code": tank.code,
        "fuel_type": tank.fuel_type,
        "capacity_liters": tank.capacity_liters,
        "low_stock_threshold_liters": threshold,
        "balance_liters": balance,
        "reserved_liters": reserved,
        "available_liters": balance - reserved,
        "low_stock": threshold is not None and balance <= threshold,
    }


def list_tanks(
    auth: Authorized, page: PageParams, *, site_id: uuid.UUID | None
) -> tuple[list[dict[str, object]], int]:
    stmt = select(Tank).where(Tank.tenant_id == auth.tenant_id)
    if not auth.scope.tenant_wide:
        stmt = stmt.where(Tank.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        stmt = stmt.where(Tank.site_id == site_id)
    total = auth.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    tanks = list(
        auth.db.scalars(
            stmt.order_by(Tank.site_id, Tank.code, Tank.fuel_tank_id)
            .offset(page.offset)
            .limit(page.page_size)
        )
    )
    return [tank_output(auth, tank) for tank in tanks], total


def create_tank(auth: Authorized, body: TankCreate) -> Tank:
    if not _in_scope(auth, body.site_id):
        raise AppError("NOT_FOUND")
    tank = Tank(
        tenant_id=auth.tenant_id,
        site_id=body.site_id,
        code=body.code,
        fuel_type=body.fuel_type,
        capacity_liters=body.capacity_liters,
        low_stock_threshold_liters=body.low_stock_threshold_liters,
        created_by=auth.user_id,
        updated_by=auth.user_id,
    )
    auth.db.add(tank)
    auth.db.flush()
    _sync_low_stock_alert(auth, tank)
    _audit(auth, "fuel.tank.create", tank.fuel_tank_id, tank.site_id)
    auth.db.commit()
    return tank


def update_threshold(auth: Authorized, tank_id: uuid.UUID, body: ThresholdUpdate) -> Tank:
    tank = _tank(auth, tank_id, lock=True)
    threshold = body.low_stock_threshold_liters
    if threshold is not None and threshold > tank.capacity_liters:
        raise AppError("VALIDATION_ERROR")
    tank.low_stock_threshold_liters = threshold
    tank.updated_by = auth.user_id
    auth.db.flush()
    _sync_low_stock_alert(auth, tank)
    _audit(auth, "fuel.stock.threshold.update", tank.fuel_tank_id, tank.site_id)
    auth.db.commit()
    return tank


def receive(auth: Authorized, tank_id: uuid.UUID, body: ReceiptCreate) -> Movement:
    tank = _tank(auth, tank_id, lock=True)
    if body.occurred_at > auth.clock.now() + timedelta(seconds=5):
        raise AppError("VALIDATION_ERROR")
    if _balance(auth.db, auth.tenant_id, tank.fuel_tank_id) + body.liters > tank.capacity_liters:
        raise AppError("CONFLICT")
    movement = Movement(
        tenant_id=auth.tenant_id,
        site_id=tank.site_id,
        fuel_tank_id=tank.fuel_tank_id,
        movement_type="RECEIPT",
        liters=body.liters,
        reference=body.reference,
        occurred_at=body.occurred_at,
        recorded_by=auth.user_id,
    )
    auth.db.add(movement)
    auth.db.flush()
    _sync_low_stock_alert(auth, tank)
    _audit(auth, "fuel.stock.receive", movement.fuel_stock_movement_id, tank.site_id)
    auth.db.commit()
    return movement


def record_stocktake(auth: Authorized, tank_id: uuid.UUID, body: StocktakeCreate) -> FuelStocktake:
    tank = _tank(auth, tank_id, lock=True)
    if body.occurred_at > auth.clock.now() + timedelta(seconds=5):
        raise AppError("VALIDATION_ERROR")
    if body.counted_liters > tank.capacity_liters:
        raise AppError("CONFLICT")
    reserved = _reserved(auth.db, auth.tenant_id, tank.fuel_tank_id)
    if body.counted_liters < reserved:
        raise AppError("CONFLICT")
    expected = _balance(auth.db, auth.tenant_id, tank.fuel_tank_id)
    delta = body.counted_liters - expected
    stocktake = FuelStocktake(
        tenant_id=auth.tenant_id,
        site_id=tank.site_id,
        fuel_tank_id=tank.fuel_tank_id,
        expected_liters=expected,
        counted_liters=body.counted_liters,
        delta_liters=delta,
        reference=body.reference,
        reason_code=body.reason_code,
        occurred_at=body.occurred_at,
        recorded_by=auth.user_id,
    )
    auth.db.add(stocktake)
    auth.db.flush()
    if delta != ZERO:
        auth.db.add(
            Movement(
                tenant_id=auth.tenant_id,
                site_id=tank.site_id,
                fuel_tank_id=tank.fuel_tank_id,
                movement_type="STOCKTAKE_IN" if delta > ZERO else "STOCKTAKE_OUT",
                liters=abs(delta),
                fuel_stocktake_id=stocktake.fuel_stocktake_id,
                occurred_at=body.occurred_at,
                recorded_by=auth.user_id,
            )
        )
    auth.db.flush()
    _sync_low_stock_alert(auth, tank)
    _audit(auth, "fuel.stocktake.record", stocktake.fuel_stocktake_id, tank.site_id)
    auth.db.commit()
    # Le contexte SET LOCAL est perdu après COMMIT ; stocktake_output relit la cuve.
    set_tenant_context(auth.db, auth.tenant_id)
    return stocktake


def list_stocktakes(
    auth: Authorized, page: PageParams, *, site_id: uuid.UUID | None
) -> tuple[list[dict[str, object]], int]:
    stmt = (
        select(FuelStocktake, Tank.code)
        .join(
            Tank,
            (Tank.tenant_id == FuelStocktake.tenant_id) & (Tank.fuel_tank_id == FuelStocktake.fuel_tank_id),
        )
        .where(FuelStocktake.tenant_id == auth.tenant_id)
    )

    if not auth.scope.tenant_wide:
        stmt = stmt.where(FuelStocktake.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        stmt = stmt.where(FuelStocktake.site_id == site_id)
    total = auth.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = auth.db.execute(
        stmt.order_by(FuelStocktake.occurred_at.desc(), FuelStocktake.fuel_stocktake_id)
        .offset(page.offset)
        .limit(page.page_size)
    ).all()
    return (
        [
            {
                "fuel_stocktake_id": entry.fuel_stocktake_id,
                "site_id": entry.site_id,
                "fuel_tank_id": entry.fuel_tank_id,
                "tank_code": tank_code,
                "expected_liters": entry.expected_liters,
                "counted_liters": entry.counted_liters,
                "delta_liters": entry.delta_liters,
                "reference": entry.reference,
                "reason_code": entry.reason_code,
                "occurred_at": entry.occurred_at,
                "recorded_by": entry.recorded_by,
                "recorded_at": entry.recorded_at,
            }
            for entry, tank_code in rows
        ],
        total,
    )


def stocktake_output(auth: Authorized, entry: FuelStocktake) -> dict[str, object]:
    tank = _tank(auth, entry.fuel_tank_id)
    return {
        "fuel_stocktake_id": entry.fuel_stocktake_id,
        "site_id": entry.site_id,
        "fuel_tank_id": entry.fuel_tank_id,
        "tank_code": tank.code,
        "expected_liters": entry.expected_liters,
        "counted_liters": entry.counted_liters,
        "delta_liters": entry.delta_liters,
        "reference": entry.reference,
        "reason_code": entry.reason_code,
        "occurred_at": entry.occurred_at,
        "recorded_by": entry.recorded_by,
        "recorded_at": entry.recorded_at,
    }


def list_stock_alerts(
    auth: Authorized,
    page: PageParams,
    *,
    site_id: uuid.UUID | None,
    active_only: bool,
) -> tuple[list[dict[str, object]], int]:
    stmt = (
        select(StockAlert, Tank.code, Tank.fuel_type)
        .join(
            Tank,
            (Tank.tenant_id == StockAlert.tenant_id) & (Tank.fuel_tank_id == StockAlert.fuel_tank_id),
        )
        .where(StockAlert.tenant_id == auth.tenant_id)
    )
    if not auth.scope.tenant_wide:
        stmt = stmt.where(StockAlert.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        stmt = stmt.where(StockAlert.site_id == site_id)
    if active_only:
        stmt = stmt.where(StockAlert.resolved_at.is_(None))
    total = auth.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = auth.db.execute(
        stmt.order_by(StockAlert.triggered_at.desc(), StockAlert.fuel_stock_alert_id)
        .offset(page.offset)
        .limit(page.page_size)
    ).all()
    return [_alert_output(alert, tank_code, fuel_type) for alert, tank_code, fuel_type in rows], total


def acknowledge_stock_alert(auth: Authorized, alert_id: uuid.UUID) -> StockAlert:
    alert = auth.db.scalar(
        select(StockAlert)
        .where(StockAlert.tenant_id == auth.tenant_id, StockAlert.fuel_stock_alert_id == alert_id)
        .with_for_update()
    )
    if alert is None or not _in_scope(auth, alert.site_id):
        raise AppError("NOT_FOUND")
    if alert.resolved_at is not None or alert.acknowledged_at is not None:
        raise AppError("CONFLICT")
    alert.acknowledged_by = auth.user_id
    alert.acknowledged_at = auth.clock.now()
    auth.db.flush()
    _audit(auth, "fuel.stock.alert.acknowledge", alert.fuel_stock_alert_id, alert.site_id)
    auth.db.commit()
    return alert


def stock_alert_output(auth: Authorized, alert: StockAlert) -> dict[str, object]:
    tank = _tank(auth, alert.fuel_tank_id)
    return _alert_output(alert, tank.code, tank.fuel_type)


def _alert_output(alert: StockAlert, tank_code: str, fuel_type: str) -> dict[str, object]:
    return {
        "fuel_stock_alert_id": alert.fuel_stock_alert_id,
        "site_id": alert.site_id,
        "fuel_tank_id": alert.fuel_tank_id,
        "tank_code": tank_code,
        "fuel_type": fuel_type,
        "threshold_liters": alert.threshold_liters,
        "balance_liters": alert.balance_liters,
        "triggered_at": alert.triggered_at,
        "acknowledged_by": alert.acknowledged_by,
        "acknowledged_at": alert.acknowledged_at,
        "resolved_at": alert.resolved_at,
        "resolution_balance_liters": alert.resolution_balance_liters,
    }


def list_suppliers(
    auth: Authorized, page: PageParams, *, site_id: uuid.UUID | None
) -> tuple[list[Supplier], int]:
    stmt = select(Supplier).where(Supplier.tenant_id == auth.tenant_id)
    if not auth.scope.tenant_wide:
        stmt = stmt.where(Supplier.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        stmt = stmt.where(Supplier.site_id == site_id)
    total = auth.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(
        auth.db.scalars(
            stmt.order_by(Supplier.site_id, Supplier.name, Supplier.fuel_supplier_id)
            .offset(page.offset)
            .limit(page.page_size)
        )
    )
    return items, total


def create_supplier(auth: Authorized, body: SupplierCreate) -> Supplier:
    if not _in_scope(auth, body.site_id):
        raise AppError("NOT_FOUND")
    supplier = Supplier(
        tenant_id=auth.tenant_id,
        site_id=body.site_id,
        code=body.code,
        name=body.name.strip(),
        created_by=auth.user_id,
        updated_by=auth.user_id,
    )
    auth.db.add(supplier)
    auth.db.flush()
    _audit(auth, "fuel.supplier.create", supplier.fuel_supplier_id, supplier.site_id)
    auth.db.commit()
    return supplier


def create_purchase(auth: Authorized, body: PurchaseCreate) -> PurchaseOrder:
    tank = _tank(auth, body.fuel_tank_id)
    supplier = auth.db.scalar(
        select(Supplier).where(
            Supplier.tenant_id == auth.tenant_id,
            Supplier.fuel_supplier_id == body.fuel_supplier_id,
            Supplier.site_id == tank.site_id,
        )
    )
    if supplier is None:
        raise AppError("NOT_FOUND")
    now = auth.clock.now()
    if body.ordered_at > now + timedelta(seconds=5) or body.ordered_at < now - timedelta(days=90):
        raise AppError("VALIDATION_ERROR")
    purchase = PurchaseOrder(
        tenant_id=auth.tenant_id,
        site_id=tank.site_id,
        fuel_supplier_id=supplier.fuel_supplier_id,
        fuel_tank_id=tank.fuel_tank_id,
        reference=body.reference,
        quantity_liters=body.quantity_liters,
        unit_price=body.unit_price,
        currency=body.currency,
        ordered_at=body.ordered_at,
        created_by=auth.user_id,
    )
    auth.db.add(purchase)
    auth.db.flush()
    _audit(auth, "fuel.purchase.create", purchase.fuel_purchase_order_id, purchase.site_id)
    auth.db.commit()
    return purchase


def decide_purchase(auth: Authorized, purchase_id: uuid.UUID, body: PurchaseDecisionCreate) -> PurchaseOrder:
    purchase = auth.db.scalar(
        select(PurchaseOrder)
        .where(
            PurchaseOrder.tenant_id == auth.tenant_id,
            PurchaseOrder.fuel_purchase_order_id == purchase_id,
        )
        .with_for_update()
    )
    if purchase is None or not _in_scope(auth, purchase.site_id):
        raise AppError("NOT_FOUND")
    if purchase.created_by == auth.user_id:
        raise AppError("CONFLICT")
    if auth.db.scalar(
        select(PurchaseDecision.fuel_purchase_decision_id).where(
            PurchaseDecision.tenant_id == auth.tenant_id,
            PurchaseDecision.fuel_purchase_order_id == purchase_id,
        )
    ):
        raise AppError("CONFLICT")
    decision = PurchaseDecision(
        tenant_id=auth.tenant_id,
        fuel_purchase_order_id=purchase.fuel_purchase_order_id,
        decision=body.decision,
        reason_code=body.reason_code,
        decided_by=auth.user_id,
    )
    auth.db.add(decision)
    auth.db.flush()
    _audit(auth, "fuel.purchase.decide", purchase.fuel_purchase_order_id, purchase.site_id)
    auth.db.commit()
    return purchase


def receive_purchase(
    auth: Authorized, purchase_id: uuid.UUID, body: PurchaseReceiptCreate
) -> PurchaseReceipt:
    purchase = auth.db.scalar(
        select(PurchaseOrder)
        .where(
            PurchaseOrder.tenant_id == auth.tenant_id,
            PurchaseOrder.fuel_purchase_order_id == purchase_id,
        )
        .with_for_update()
    )
    if purchase is None or not _in_scope(auth, purchase.site_id):
        raise AppError("NOT_FOUND")
    decision = auth.db.scalar(
        select(PurchaseDecision).where(
            PurchaseDecision.tenant_id == auth.tenant_id,
            PurchaseDecision.fuel_purchase_order_id == purchase_id,
        )
    )
    if decision is None or decision.decision != "APPROVED":
        raise AppError("CONFLICT")
    if body.occurred_at < purchase.ordered_at or body.occurred_at > auth.clock.now() + timedelta(seconds=5):
        raise AppError("VALIDATION_ERROR")
    received = _purchase_received(auth.db, auth.tenant_id, purchase.fuel_purchase_order_id)
    if body.liters > purchase.quantity_liters - received:
        raise AppError("CONFLICT")
    tank = _tank(auth, purchase.fuel_tank_id, lock=True)
    if _balance(auth.db, auth.tenant_id, tank.fuel_tank_id) + body.liters > tank.capacity_liters:
        raise AppError("CONFLICT")
    receipt = PurchaseReceipt(
        tenant_id=auth.tenant_id,
        site_id=purchase.site_id,
        fuel_purchase_order_id=purchase.fuel_purchase_order_id,
        fuel_tank_id=purchase.fuel_tank_id,
        liters=body.liters,
        delivery_reference=body.delivery_reference,
        occurred_at=body.occurred_at,
        recorded_by=auth.user_id,
    )
    auth.db.add(receipt)
    auth.db.flush()
    auth.db.add(
        Movement(
            tenant_id=auth.tenant_id,
            site_id=purchase.site_id,
            fuel_tank_id=purchase.fuel_tank_id,
            movement_type="PURCHASE_RECEIPT",
            liters=body.liters,
            fuel_purchase_receipt_id=receipt.fuel_purchase_receipt_id,
            occurred_at=body.occurred_at,
            recorded_by=auth.user_id,
        )
    )
    auth.db.flush()
    _sync_low_stock_alert(auth, tank)
    _audit(auth, "fuel.purchase.receive", receipt.fuel_purchase_receipt_id, receipt.site_id)
    auth.db.commit()
    return receipt


def list_purchases(
    auth: Authorized,
    page: PageParams,
    *,
    site_id: uuid.UUID | None,
    status: str | None,
) -> tuple[list[dict[str, object]], int]:
    received = (
        select(
            PurchaseReceipt.tenant_id.label("tenant_id"),
            PurchaseReceipt.fuel_purchase_order_id.label("purchase_id"),
            func.sum(PurchaseReceipt.liters).label("received_liters"),
        )
        .group_by(PurchaseReceipt.tenant_id, PurchaseReceipt.fuel_purchase_order_id)
        .subquery()
    )
    stmt = (
        select(
            PurchaseOrder,
            Supplier.code,
            Supplier.name,
            Tank.code,
            Tank.fuel_type,
            PurchaseDecision,
            func.coalesce(received.c.received_liters, ZERO),
        )
        .join(
            Supplier,
            (Supplier.tenant_id == PurchaseOrder.tenant_id)
            & (Supplier.fuel_supplier_id == PurchaseOrder.fuel_supplier_id),
        )
        .join(
            Tank,
            (Tank.tenant_id == PurchaseOrder.tenant_id) & (Tank.fuel_tank_id == PurchaseOrder.fuel_tank_id),
        )
        .outerjoin(
            PurchaseDecision,
            (PurchaseDecision.tenant_id == PurchaseOrder.tenant_id)
            & (PurchaseDecision.fuel_purchase_order_id == PurchaseOrder.fuel_purchase_order_id),
        )
        .outerjoin(
            received,
            (received.c.tenant_id == PurchaseOrder.tenant_id)
            & (received.c.purchase_id == PurchaseOrder.fuel_purchase_order_id),
        )
        .where(PurchaseOrder.tenant_id == auth.tenant_id)
    )
    if not auth.scope.tenant_wide:
        stmt = stmt.where(PurchaseOrder.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        stmt = stmt.where(PurchaseOrder.site_id == site_id)
    rows = auth.db.execute(stmt.order_by(PurchaseOrder.ordered_at.desc())).all()
    items = [
        _purchase_output(
            order,
            supplier_code,
            supplier_name,
            tank_code,
            fuel_type,
            decision,
            Decimal(received_liters),
        )
        for order, supplier_code, supplier_name, tank_code, fuel_type, decision, received_liters in rows
    ]
    if status is not None:
        items = [item for item in items if item["status"] == status]
    total = len(items)
    return items[page.offset : page.offset + page.page_size], total


def purchase_output(auth: Authorized, purchase: PurchaseOrder) -> dict[str, object]:
    supplier = auth.db.scalar(
        select(Supplier).where(
            Supplier.tenant_id == auth.tenant_id,
            Supplier.fuel_supplier_id == purchase.fuel_supplier_id,
        )
    )
    tank = _tank(auth, purchase.fuel_tank_id)
    decision = auth.db.scalar(
        select(PurchaseDecision).where(
            PurchaseDecision.tenant_id == auth.tenant_id,
            PurchaseDecision.fuel_purchase_order_id == purchase.fuel_purchase_order_id,
        )
    )
    received = _purchase_received(auth.db, auth.tenant_id, purchase.fuel_purchase_order_id)
    return _purchase_output(
        purchase,
        supplier.code if supplier else "?",
        supplier.name if supplier else "?",
        tank.code,
        tank.fuel_type,
        decision,
        received,
    )


def _purchase_received(db: Session, tenant_id: uuid.UUID, purchase_id: uuid.UUID) -> Decimal:
    value = db.scalar(
        select(func.coalesce(func.sum(PurchaseReceipt.liters), ZERO)).where(
            PurchaseReceipt.tenant_id == tenant_id,
            PurchaseReceipt.fuel_purchase_order_id == purchase_id,
        )
    )
    return Decimal(value or ZERO)


def _purchase_output(
    purchase: PurchaseOrder,
    supplier_code: str,
    supplier_name: str,
    tank_code: str,
    fuel_type: str,
    decision: PurchaseDecision | None,
    received: Decimal,
) -> dict[str, object]:
    if decision is None:
        status = "PENDING_APPROVAL"
    elif decision.decision == "REJECTED":
        status = "REJECTED"
    elif received == ZERO:
        status = "APPROVED"
    elif received < purchase.quantity_liters:
        status = "PARTIALLY_RECEIVED"
    else:
        status = "RECEIVED"
    return {
        "fuel_purchase_order_id": purchase.fuel_purchase_order_id,
        "site_id": purchase.site_id,
        "fuel_supplier_id": purchase.fuel_supplier_id,
        "supplier_code": supplier_code,
        "supplier_name": supplier_name,
        "fuel_tank_id": purchase.fuel_tank_id,
        "tank_code": tank_code,
        "fuel_type": fuel_type,
        "reference": purchase.reference,
        "quantity_liters": purchase.quantity_liters,
        "received_liters": received,
        "remaining_liters": purchase.quantity_liters - received,
        "unit_price": purchase.unit_price,
        "total_amount": purchase.quantity_liters * purchase.unit_price,
        "currency": purchase.currency,
        "ordered_at": purchase.ordered_at,
        "created_by": purchase.created_by,
        "created_at": purchase.created_at,
        "status": status,
        "decided_by": decision.decided_by if decision else None,
        "decided_at": decision.decided_at if decision else None,
        "reason_code": decision.reason_code if decision else None,
    }


def _validate_vehicle_and_driver(auth: Authorized, body: IssueCreate, tank: Tank) -> tuple[Vehicle, Driver]:
    vehicle = auth.db.scalar(
        select(Vehicle)
        .where(
            Vehicle.tenant_id == auth.tenant_id,
            Vehicle.vehicle_id == body.vehicle_id,
            Vehicle.site_id == tank.site_id,
        )
        .with_for_update()
    )
    if vehicle is None or vehicle.status == "RETIRED":
        raise AppError("NOT_FOUND")
    if vehicle.fuel_type in {"DIESEL", "PETROL"} and vehicle.fuel_type != tank.fuel_type:
        raise AppError("CONFLICT")
    driver = auth.db.scalar(
        select(Driver).where(
            Driver.tenant_id == auth.tenant_id,
            Driver.driver_id == body.driver_id,
            Driver.site_id == tank.site_id,
            Driver.status == "ACTIVE",
        )
    )
    now = auth.clock.now()
    assignment = auth.db.scalar(
        select(VehicleAssignment.vehicle_assignment_id)
        .where(
            VehicleAssignment.tenant_id == auth.tenant_id,
            VehicleAssignment.vehicle_id == body.vehicle_id,
            VehicleAssignment.driver_id == body.driver_id,
            VehicleAssignment.site_id == tank.site_id,
            VehicleAssignment.status == "ACTIVE",
            VehicleAssignment.valid_from <= now,
            or_(VehicleAssignment.valid_to.is_(None), VehicleAssignment.valid_to > now),
        )
        .limit(1)
    )
    if driver is None or assignment is None:
        raise AppError("CONFLICT")
    category = auth.db.get(VehicleCategory, vehicle.vehicle_category_id)
    allowed = set()
    if category and category.has_odometer:
        allowed.add("ODOMETER")
    if category and category.has_hour_meter:
        allowed.add("HOUR_METER")
    if allowed and (body.meter_kind not in allowed or body.meter_value is None):
        raise AppError("VALIDATION_ERROR")
    if not allowed and (body.meter_kind is not None or body.meter_value is not None):
        raise AppError("VALIDATION_ERROR")
    if body.meter_kind is not None and body.meter_value is not None:
        previous = auth.db.scalar(
            select(Issue)
            .outerjoin(
                Decision,
                (Decision.tenant_id == Issue.tenant_id) & (Decision.fuel_issue_id == Issue.fuel_issue_id),
            )
            .where(
                Issue.tenant_id == auth.tenant_id,
                Issue.vehicle_id == body.vehicle_id,
                Issue.meter_kind == body.meter_kind,
                Decision.decision == "APPROVED",
            )
            .order_by(Issue.requested_at.desc(), Issue.fuel_issue_id)
            .limit(1)
        )
        if previous and (
            body.meter_value < (previous.meter_value or ZERO) or body.requested_at < previous.requested_at
        ):
            raise AppError("CONFLICT")
    return vehicle, driver


def create_issue(auth: Authorized, body: IssueCreate) -> Issue:
    tank = _tank(auth, body.fuel_tank_id, lock=True)
    now = auth.clock.now()
    if body.requested_at > now + timedelta(seconds=5) or body.requested_at < now - timedelta(hours=24):
        raise AppError("VALIDATION_ERROR")
    _validate_vehicle_and_driver(auth, body, tank)
    available = _balance(auth.db, auth.tenant_id, tank.fuel_tank_id) - _reserved(
        auth.db, auth.tenant_id, tank.fuel_tank_id
    )
    if body.liters > available:
        raise AppError("CONFLICT")
    issue = Issue(
        tenant_id=auth.tenant_id,
        site_id=tank.site_id,
        fuel_tank_id=tank.fuel_tank_id,
        vehicle_id=body.vehicle_id,
        driver_id=body.driver_id,
        liters=body.liters,
        meter_kind=body.meter_kind,
        meter_value=body.meter_value,
        full_tank=body.full_tank,
        requested_at=body.requested_at,
        requested_by=auth.user_id,
    )
    auth.db.add(issue)
    auth.db.flush()
    _audit(auth, "fuel.issue.request", issue.fuel_issue_id, issue.site_id)
    auth.db.commit()
    return issue


def decide_issue(auth: Authorized, issue_id: uuid.UUID, body: DecisionCreate) -> Issue:
    issue = auth.db.scalar(
        select(Issue).where(Issue.tenant_id == auth.tenant_id, Issue.fuel_issue_id == issue_id)
    )
    if issue is None or not _in_scope(auth, issue.site_id):
        raise AppError("NOT_FOUND")
    if issue.requested_by == auth.user_id:
        raise AppError("CONFLICT")
    if auth.db.scalar(
        select(Decision.fuel_issue_decision_id).where(
            Decision.tenant_id == auth.tenant_id, Decision.fuel_issue_id == issue_id
        )
    ):
        raise AppError("CONFLICT")
    tank = _tank(auth, issue.fuel_tank_id, lock=True)
    if body.decision == "APPROVED":
        if _balance(auth.db, auth.tenant_id, tank.fuel_tank_id) < issue.liters:
            raise AppError("CONFLICT")
        if issue.meter_kind is not None and issue.meter_value is not None:
            latest = auth.db.scalar(
                select(Issue)
                .outerjoin(
                    Decision,
                    (Decision.tenant_id == Issue.tenant_id) & (Decision.fuel_issue_id == Issue.fuel_issue_id),
                )
                .where(
                    Issue.tenant_id == auth.tenant_id,
                    Issue.vehicle_id == issue.vehicle_id,
                    Issue.meter_kind == issue.meter_kind,
                    Decision.decision == "APPROVED",
                )
                .order_by(Issue.requested_at.desc(), Issue.fuel_issue_id)
                .limit(1)
            )
            if latest and (
                issue.meter_value < (latest.meter_value or ZERO) or issue.requested_at < latest.requested_at
            ):
                raise AppError("CONFLICT")
        auth.db.add(
            Movement(
                tenant_id=auth.tenant_id,
                site_id=issue.site_id,
                fuel_tank_id=issue.fuel_tank_id,
                movement_type="ISSUE",
                liters=issue.liters,
                fuel_issue_id=issue.fuel_issue_id,
                occurred_at=issue.requested_at,
                recorded_by=auth.user_id,
            )
        )
        auth.db.flush()
        _sync_low_stock_alert(auth, tank)
    decision = Decision(
        tenant_id=auth.tenant_id,
        fuel_issue_id=issue.fuel_issue_id,
        decision=body.decision,
        reason_code=body.reason_code,
        decided_by=auth.user_id,
    )
    auth.db.add(decision)
    auth.db.flush()
    _audit(auth, "fuel.issue.decide", issue.fuel_issue_id, issue.site_id)
    auth.db.commit()
    # COMMIT clôt SET LOCAL ; rétablir le contexte RLS pour la projection de réponse.
    set_tenant_context(auth.db, auth.tenant_id)
    return issue


def list_issues(
    auth: Authorized, page: PageParams, *, site_id: uuid.UUID | None, status: str | None
) -> tuple[list[dict[str, object]], int]:
    stmt = (
        select(Issue, Tank.code, Tank.fuel_type, Vehicle.fleet_number, Decision)
        .join(Tank, (Tank.tenant_id == Issue.tenant_id) & (Tank.fuel_tank_id == Issue.fuel_tank_id))
        .join(Vehicle, (Vehicle.tenant_id == Issue.tenant_id) & (Vehicle.vehicle_id == Issue.vehicle_id))
        .outerjoin(
            Decision,
            (Decision.tenant_id == Issue.tenant_id) & (Decision.fuel_issue_id == Issue.fuel_issue_id),
        )
        .where(Issue.tenant_id == auth.tenant_id)
    )
    if not auth.scope.tenant_wide:
        stmt = stmt.where(Issue.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        stmt = stmt.where(Issue.site_id == site_id)
    if status == "PENDING_APPROVAL":
        stmt = stmt.where(Decision.fuel_issue_decision_id.is_(None))
    elif status == "APPROVED":
        stmt = stmt.where(Decision.decision == "APPROVED")
    elif status == "REJECTED":
        stmt = stmt.where(Decision.decision == "REJECTED")
    total = auth.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = auth.db.execute(
        stmt.order_by(Issue.requested_at.desc(), Issue.fuel_issue_id)
        .offset(page.offset)
        .limit(page.page_size)
    ).all()
    return (
        [
            {
                "fuel_issue_id": issue.fuel_issue_id,
                "site_id": issue.site_id,
                "fuel_tank_id": issue.fuel_tank_id,
                "tank_code": tank_code,
                "fuel_type": fuel_type,
                "vehicle_id": issue.vehicle_id,
                "vehicle_fleet_number": fleet_number,
                "driver_id": issue.driver_id,
                "liters": issue.liters,
                "meter_kind": issue.meter_kind,
                "meter_value": issue.meter_value,
                "full_tank": issue.full_tank,
                "requested_at": issue.requested_at,
                "requested_by": issue.requested_by,
                "status": decision.decision if decision else "PENDING_APPROVAL",
                "decided_by": decision.decided_by if decision else None,
                "decided_at": decision.decided_at if decision else None,
                "reason_code": decision.reason_code if decision else None,
            }
            for issue, tank_code, fuel_type, fleet_number, decision in rows
        ],
        total,
    )


def issue_output(auth: Authorized, issue: Issue) -> dict[str, object]:
    tank = auth.db.scalar(
        select(Tank).where(Tank.tenant_id == auth.tenant_id, Tank.fuel_tank_id == issue.fuel_tank_id)
    )
    vehicle = auth.db.scalar(
        select(Vehicle).where(Vehicle.tenant_id == auth.tenant_id, Vehicle.vehicle_id == issue.vehicle_id)
    )
    decision = auth.db.scalar(
        select(Decision).where(
            Decision.tenant_id == auth.tenant_id, Decision.fuel_issue_id == issue.fuel_issue_id
        )
    )
    return {
        "fuel_issue_id": issue.fuel_issue_id,
        "site_id": issue.site_id,
        "fuel_tank_id": issue.fuel_tank_id,
        "tank_code": tank.code if tank else "?",
        "fuel_type": tank.fuel_type if tank else "DIESEL",
        "vehicle_id": issue.vehicle_id,
        "vehicle_fleet_number": vehicle.fleet_number if vehicle else "?",
        "driver_id": issue.driver_id,
        "liters": issue.liters,
        "meter_kind": issue.meter_kind,
        "meter_value": issue.meter_value,
        "full_tank": issue.full_tank,
        "requested_at": issue.requested_at,
        "requested_by": issue.requested_by,
        "status": decision.decision if decision else "PENDING_APPROVAL",
        "decided_by": decision.decided_by if decision else None,
        "decided_at": decision.decided_at if decision else None,
        "reason_code": decision.reason_code if decision else None,
    }
