import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import AuditedColumns


class Driver(AuditedColumns, Base):
    __tablename__ = "driver"
    __mapper_args__ = {"eager_defaults": True}

    driver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Liaison compte ↔ conducteur hors lot 1 (D-16) : jamais écrite par l'API.
    user_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    employee_number: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    phone: Mapped[str | None] = mapped_column(String)
    employment_type: Mapped[str] = mapped_column(String, nullable=False, server_default="EMPLOYEE")
    external_company_name: Mapped[str | None] = mapped_column(String)
    hire_date: Mapped[date | None] = mapped_column(Date)
    exit_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="ACTIVE")
    unavailability_reason: Mapped[str | None] = mapped_column(String)
    unavailable_until: Mapped[date | None] = mapped_column(Date)
    suspension_reason_code: Mapped[str | None] = mapped_column(String)
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DriverLicense(AuditedColumns, Base):
    __tablename__ = "driver_license"
    __mapper_args__ = {"eager_defaults": True}

    driver_license_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    license_number: Mapped[str] = mapped_column(String, nullable=False)
    category_code: Mapped[str] = mapped_column(String, nullable=False)
    issuing_authority: Mapped[str | None] = mapped_column(String)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="VALID")
    status_note: Mapped[str | None] = mapped_column(String)
    document_reference: Mapped[str | None] = mapped_column(String)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DriverQualification(AuditedColumns, Base):
    __tablename__ = "driver_qualification"
    __mapper_args__ = {"eager_defaults": True}

    driver_qualification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qualification_type: Mapped[str] = mapped_column(String, nullable=False)
    vehicle_category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    site_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="VALID")
    issued_by_name: Mapped[str | None] = mapped_column(String)
    reference: Mapped[str | None] = mapped_column(String)
    restrictions: Mapped[str | None] = mapped_column(String)
