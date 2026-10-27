import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import AuditedColumns


class SiteLocation(AuditedColumns, Base):
    """Lieu d'un site : point de chargement, de déchargement, stock, concasseur, pont-bascule…"""

    __tablename__ = "site_location"
    __mapper_args__ = {"eager_defaults": True}

    site_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="ACTIVE")


class Material(AuditedColumns, Base):
    __tablename__ = "material"
    __mapper_args__ = {"eager_defaults": True}

    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    is_waste: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="ACTIVE")


class Mission(AuditedColumns, Base):
    __tablename__ = "mission"
    __mapper_args__ = {"eager_defaults": True}

    mission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vehicle_assignment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Copiés de l'affectation (historique) ; ne changent que par réaffectation explicite (US-2.03).
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    origin_location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    destination_location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    material_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    planned_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_rotations: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="ASSIGNED")
    status_before_suspension: Mapped[str | None] = mapped_column(String)
    status_reason: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(String)


class MissionEvent(Base):
    """Ajout seul (trigger) : la chronologie d'une mission ne se réécrit jamais (RM-085)."""

    __tablename__ = "mission_event"
    __mapper_args__ = {"eager_defaults": True}

    mission_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    mission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vehicle_assignment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    from_status: Mapped[str | None] = mapped_column(String)
    to_status: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    source: Mapped[str] = mapped_column(String, nullable=False, server_default="DISPATCHER")
    client_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reason: Mapped[str | None] = mapped_column(String)


class Rotation(Base):
    """Cycle chargement → déchargement, dérivé des événements ; aucun tonnage (RM-070, RM-072)."""

    __tablename__ = "rotation"
    __mapper_args__ = {"eager_defaults": True}

    rotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    mission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    loading_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    loaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unloading_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="OPEN")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    row_version: Mapped[int] = mapped_column(Integer, server_default=text("1"), nullable=False)
