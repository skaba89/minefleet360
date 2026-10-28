import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Computed,
    Date,
    DateTime,
    FetchedValue,
    Integer,
    Numeric,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import AuditedColumns


class VehicleCategory(AuditedColumns, Base):
    __tablename__ = "vehicle_category"
    __mapper_args__ = {"eager_defaults": True}

    vehicle_category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    label_fr: Mapped[str] = mapped_column(String, nullable=False)
    family: Mapped[str] = mapped_column(String, nullable=False)
    requires_driver: Mapped[bool] = mapped_column(Boolean, nullable=False)
    requires_internal_authorization: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_odometer: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_hour_meter: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)


class VehicleCategoryLicense(Base):
    __tablename__ = "vehicle_category_license_category"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    vehicle_category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    license_category_code: Mapped[str] = mapped_column(String, primary_key=True)


class Vehicle(AuditedColumns, Base):
    __tablename__ = "vehicle"
    __mapper_args__ = {"eager_defaults": True}

    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vehicle_category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fleet_number: Mapped[str] = mapped_column(String, nullable=False)
    fleet_number_norm: Mapped[str] = mapped_column(String, Computed("lower(btrim(fleet_number))"))
    registration_number: Mapped[str | None] = mapped_column(String)
    registration_norm: Mapped[str | None] = mapped_column(
        String, Computed("upper(regexp_replace(registration_number, '[\\s\\-]', '', 'g'))")
    )
    serial_number: Mapped[str | None] = mapped_column(String)
    make: Mapped[str | None] = mapped_column(String)
    model: Mapped[str | None] = mapped_column(String)
    model_year: Mapped[int | None] = mapped_column(SmallInteger)
    ownership_type: Mapped[str] = mapped_column(String, nullable=False, server_default="OWNED")
    fuel_type: Mapped[str | None] = mapped_column(String)
    # Capacité NOMINALE constructeur : jamais une mesure de tonnage (H10).
    rated_payload_kg: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="AVAILABLE")
    status_reason_code: Mapped[str | None] = mapped_column(String)
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), server_onupdate=FetchedValue(), nullable=False
    )
    commissioned_on: Mapped[date | None] = mapped_column(Date)
    decommissioned_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(String)


class VehicleStatusHistory(Base):
    """Ajout seul, alimentée par trigger (DB-16) : jamais écrite par l'application."""

    __tablename__ = "vehicle_status_history"

    vehicle_status_history_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String)
    to_status: Mapped[str] = mapped_column(String, nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class VehicleMeterReading(Base):
    """Relevé de compteur, AJOUT SEUL (trigger) : une erreur se corrige par une remise à zéro motivée."""

    __tablename__ = "vehicle_meter_reading"
    __mapper_args__ = {"eager_defaults": True}

    vehicle_meter_reading_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    meter_kind: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 1), nullable=False)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False, server_default="MANUAL")
    reset_reason: Mapped[str | None] = mapped_column(String)
    recorded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class VehicleDocument(AuditedColumns, Base):
    """Document réglementaire (assurance, visite technique…) ; validité dérivée des dates (D-03)."""

    __tablename__ = "vehicle_document"
    __mapper_args__ = {"eager_defaults": True}

    vehicle_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    doc_type: Mapped[str] = mapped_column(String, nullable=False)
    reference: Mapped[str] = mapped_column(String, nullable=False)
    issuer: Mapped[str | None] = mapped_column(String)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="VALID")
    status_reason: Mapped[str | None] = mapped_column(String)
    # Décision C-06 prise document par document : bloque l'affectation une fois échu (RM-104).
    blocks_assignment: Mapped[bool] = mapped_column(Boolean, nullable=False)
