import uuid

from sqlalchemy import Boolean, Computed, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import AuditedColumns


class Tenant(AuditedColumns, Base):
    __tablename__ = "tenant"
    __mapper_args__ = {"eager_defaults": True}

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    code: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False, server_default="CUSTOMER")
    legal_name: Mapped[str] = mapped_column(String, nullable=False)
    legal_name_norm: Mapped[str] = mapped_column(
        String, Computed("lower(regexp_replace(btrim(legal_name), '\\s+', ' ', 'g'))", persisted=True)
    )
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="ACTIVE")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    default_timezone: Mapped[str] = mapped_column(String, nullable=False, server_default="Africa/Conakry")
    default_locale: Mapped[str] = mapped_column(String, nullable=False, server_default="fr-GN")
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, server_default="GN")
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, server_default="GNF")


class Site(AuditedColumns, Base):
    __tablename__ = "site"
    __mapper_args__ = {"eager_defaults": True}

    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    site_type: Mapped[str] = mapped_column(String, nullable=False)
    timezone: Mapped[str | None] = mapped_column(String)
    # `location geography(Point,4326)` existe en base ; non exposée au lot 1a (pas de story).
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="ACTIVE")
