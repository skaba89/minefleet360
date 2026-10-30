"""Modèles de fondation du catalogue et des stocks de pièces détachées."""

import uuid
from decimal import Decimal

from sqlalchemy import Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SparePart(Base):
    __tablename__ = "spare_part"
    __mapper_args__ = {"eager_defaults": True}

    spare_part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    unit: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'EACH'"))


class SparePartStore(Base):
    __tablename__ = "spare_part_store"
    __mapper_args__ = {"eager_defaults": True}

    spare_part_store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)


class SparePartBalance(Base):
    __tablename__ = "spare_part_balance"
    __mapper_args__ = {"eager_defaults": True}

    spare_part_balance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    spare_part_store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    spare_part_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    on_hand: Mapped[Decimal] = mapped_column(Numeric(16, 3), nullable=False, server_default=text("0"))
    reserved: Mapped[Decimal] = mapped_column(Numeric(16, 3), nullable=False, server_default=text("0"))
    low_stock_threshold: Mapped[Decimal] = mapped_column(
        Numeric(16, 3), nullable=False, server_default=text("0")
    )
