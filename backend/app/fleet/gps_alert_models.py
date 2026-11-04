"""Modèles ORM des alertes GPS (migration 0061) ; contraintes et RLS dans la migration."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Float, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SiteGpsPolicy(Base):
    __tablename__ = "site_gps_policy"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    speed_limit_kmh: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    updated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class GpsAlert(Base):
    __tablename__ = "gps_alert"
    __mapper_args__ = {"eager_defaults": True}

    gps_alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    speed_limit_kmh: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    peak_speed_kmh: Mapped[float | None] = mapped_column(Float)
    site_geofence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledgement_note: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
