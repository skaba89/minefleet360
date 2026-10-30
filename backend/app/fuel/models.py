import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import AuditedColumns


class FuelTank(AuditedColumns, Base):
    __tablename__ = "fuel_tank"
    __mapper_args__ = {"eager_defaults": True}

    fuel_tank_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    fuel_type: Mapped[str] = mapped_column(String, nullable=False)
    capacity_liters: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    low_stock_threshold_liters: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))


class FuelPump(AuditedColumns, Base):
    """Pompe rattachée à une seule cuve sur un site."""

    __tablename__ = "fuel_pump"
    __mapper_args__ = {"eager_defaults": True}

    fuel_pump_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fuel_tank_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)


class FuelPumpMeterReading(Base):
    """Relevé cumulé immuable du compteur d'une pompe."""

    __tablename__ = "fuel_pump_meter_reading"
    __mapper_args__ = {"eager_defaults": True}

    fuel_pump_meter_reading_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fuel_pump_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    cumulative_liters: Mapped[Decimal] = mapped_column(Numeric(16, 3), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_reference: Mapped[str] = mapped_column(String, nullable=False)
    recorded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class FuelStockAlert(Base):
    """Cycle d'alerte persistant tant qu'une cuve reste sous son seuil."""

    __tablename__ = "fuel_stock_alert"
    __mapper_args__ = {"eager_defaults": True}

    fuel_stock_alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fuel_tank_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    threshold_liters: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    balance_liters: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_balance_liters: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))


class FuelSupplier(AuditedColumns, Base):
    __tablename__ = "fuel_supplier"
    __mapper_args__ = {"eager_defaults": True}

    fuel_supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)


class FuelPurchaseOrder(Base):
    """Commande immuable ; sa décision et ses livraisons sont des événements séparés."""

    __tablename__ = "fuel_purchase_order"
    __mapper_args__ = {"eager_defaults": True}

    fuel_purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fuel_supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fuel_tank_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reference: Mapped[str] = mapped_column(String, nullable=False)
    quantity_liters: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class FuelPurchaseDecision(Base):
    __tablename__ = "fuel_purchase_decision"
    __mapper_args__ = {"eager_defaults": True}

    fuel_purchase_decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fuel_purchase_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String)
    decided_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class FuelPurchaseReceipt(Base):
    __tablename__ = "fuel_purchase_receipt"
    __mapper_args__ = {"eager_defaults": True}

    fuel_purchase_receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fuel_purchase_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fuel_tank_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    liters: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    delivery_reference: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class FuelIssue(Base):
    """Demande de ravitaillement immuable ; approbation/refus et sortie sont des événements distincts."""

    __tablename__ = "fuel_issue"
    __mapper_args__ = {"eager_defaults": True}

    fuel_issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fuel_tank_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fuel_pump_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    liters: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    meter_kind: Mapped[str | None] = mapped_column(String)
    meter_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 1))
    full_tank: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class FuelIssueDecision(Base):
    """Décision append-only, séparée de la demande de ravitaillement."""

    __tablename__ = "fuel_issue_decision"
    __mapper_args__ = {"eager_defaults": True}

    fuel_issue_decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fuel_issue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String)
    decided_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class FuelStocktake(Base):
    """Relevé physique immuable et écart calculé par rapport au journal."""

    __tablename__ = "fuel_stocktake"
    __mapper_args__ = {"eager_defaults": True}

    fuel_stocktake_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fuel_tank_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    expected_liters: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    counted_liters: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    delta_liters: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    reference: Mapped[str] = mapped_column(String, nullable=False)
    reason_code: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class FuelStockMovement(Base):
    """Ledger append-only : réception, sortie approuvée ou correction d'inventaire."""

    __tablename__ = "fuel_stock_movement"
    __mapper_args__ = {"eager_defaults": True}

    fuel_stock_movement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fuel_tank_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    movement_type: Mapped[str] = mapped_column(String, nullable=False)
    liters: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    reference: Mapped[str | None] = mapped_column(String)
    fuel_issue_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    fuel_stocktake_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    fuel_purchase_receipt_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
