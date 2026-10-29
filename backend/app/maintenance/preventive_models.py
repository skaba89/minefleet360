"""Modèles ORM du lot 3b : plans et échéances de maintenance préventive.

Les contraintes d'intégrité, clés étrangères composites et politiques RLS sont
définies dans la migration Alembic 0019 ; aucun DDL n'est créé par ces classes.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import AuditedColumns


class MaintenancePlan(AuditedColumns, Base):
    """Version d'un plan d'entretien rattachée à un véhicule d'un tenant."""

    __tablename__ = "maintenance_plan"
    __mapper_args__ = {"eager_defaults": True}

    maintenance_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    km_interval: Mapped[Decimal | None] = mapped_column(Numeric(12, 1))
    hours_interval: Mapped[Decimal | None] = mapped_column(Numeric(12, 1))
    days_interval: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    suspension_reason: Mapped[str | None] = mapped_column(String)


class MaintenanceDue(Base):
    """Échéance calculée ; la déduplication est imposée par PostgreSQL."""

    __tablename__ = "maintenance_due"
    __mapper_args__ = {"eager_defaults": True}

    maintenance_due_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    maintenance_plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    trigger_kind: Mapped[str] = mapped_column(String, nullable=False)
    trigger_key: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="DUE")
    due_on: Mapped[date | None] = mapped_column(Date)
    due_meter: Mapped[Decimal | None] = mapped_column(Numeric(12, 1))
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class MeterReconciliationApproval(Base):
    """Approbation durable d'un cumul, ajout seul et liée au tenant/site."""

    __tablename__ = "maintenance_meter_reconciliation_approval"
    __mapper_args__ = {"eager_defaults": True}

    approval_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    meter_kind: Mapped[str] = mapped_column(String, nullable=False)
    baseline_total: Mapped[Decimal] = mapped_column(Numeric(12, 1), nullable=False)
    current_total: Mapped[Decimal] = mapped_column(Numeric(12, 1), nullable=False)
    reconciliation_reference: Mapped[str] = mapped_column(String, nullable=False)
    approved_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
