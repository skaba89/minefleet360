import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import AuditedColumns


class MaintenanceCounter(Base):
    """Dernier numéro d'OT du tenant (numéro lisible, attribué sous verrou de ligne)."""

    __tablename__ = "maintenance_counter"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class WorkOrder(AuditedColumns, Base):
    __tablename__ = "work_order"
    __mapper_args__ = {"eager_defaults": True}

    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    mission_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(String, nullable=False, server_default="CORRECTIVE")
    priority: Mapped[str] = mapped_column(String, nullable=False)
    symptom_code: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    # Panne bloquante : le véhicule est immobilisé au signalement (D-44).
    immobilize: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="REQUESTED")
    status_reason: Mapped[str | None] = mapped_column(String)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    expected_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    diagnosis: Mapped[str | None] = mapped_column(String)
    work_done: Mapped[str | None] = mapped_column(String)
    parts_note: Mapped[str | None] = mapped_column(String)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reported_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class WorkOrderEvent(Base):
    """Transition d'un OT, AJOUT SEUL (trigger) : chronologie et base des durées d'immobilisation."""

    __tablename__ = "work_order_event"
    __mapper_args__ = {"eager_defaults": True}

    work_order_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    work_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    from_status: Mapped[str | None] = mapped_column(String)
    to_status: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(String)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class WorkOrderLabour(Base):
    """Temps passé par un mécanicien, AJOUT SEUL (trigger)."""

    __tablename__ = "work_order_labour"
    __mapper_args__ = {"eager_defaults": True}

    work_order_labour_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    work_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    mechanic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    performed_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String)
    recorded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
