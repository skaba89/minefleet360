import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import AuditedColumns


class Tyre(AuditedColumns, Base):
    __tablename__ = "tyre"
    __mapper_args__ = {"eager_defaults": True}

    tyre_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    serial_number: Mapped[str] = mapped_column(String, nullable=False)
    brand: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    size: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    spare_part_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    purchase_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    currency: Mapped[str | None] = mapped_column(String)
    initial_tread_mm: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False)
    scrap_tread_mm: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False)
    nominal_pressure_kpa: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="IN_STOCK")
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    position_code: Mapped[str | None] = mapped_column(String)
    mounted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retread_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_tread_mm: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    last_pressure_kpa: Mapped[int | None] = mapped_column(Integer)
    last_inspected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scrap_reason: Mapped[str | None] = mapped_column(String)


class TyreEvent(Base):
    """Chronologie d'un pneu, AJOUT SEUL (trigger) : montages, contrôles, réparations, rebut."""

    __tablename__ = "tyre_event"
    __mapper_args__ = {"eager_defaults": True}

    tyre_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tyre_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    position_code: Mapped[str | None] = mapped_column(String)
    odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 1))
    hour_meter: Mapped[Decimal | None] = mapped_column(Numeric(12, 1))
    tread_mm: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    pressure_kpa: Mapped[int | None] = mapped_column(Integer)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    currency: Mapped[str | None] = mapped_column(String)
    reason_code: Mapped[str | None] = mapped_column(String)
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(String)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
