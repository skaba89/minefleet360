import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Computed, DateTime, String, text
from sqlalchemy.dialects.postgresql import JSONB, TSTZRANGE, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import AuditedColumns


class VehicleAssignment(AuditedColumns, Base):
    """Affectation conducteur ↔ véhicule sur `[valid_from, valid_to)` (D-04) ; chevauchement exclu en base."""

    __tablename__ = "vehicle_assignment"
    __mapper_args__ = {"eager_defaults": True}

    vehicle_assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_during: Mapped[Any] = mapped_column(TSTZRANGE, Computed("tstzrange(valid_from, valid_to, '[)')"))
    shift_code: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="PLANNED")
    status_reason: Mapped[str | None] = mapped_column(String)
    # Identifiants et dates des pièces retenues à la création (DB-41) : jamais de n° de permis.
    eligibility_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
