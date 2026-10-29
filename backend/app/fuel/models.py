import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, text
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
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    liters: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    meter_kind: Mapped[str | None] = mapped_column(String)
    meter_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 1))
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
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
