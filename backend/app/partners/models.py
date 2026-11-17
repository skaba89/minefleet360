import uuid
from decimal import Decimal

from sqlalchemy import Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import AuditedColumns


class Subcontractor(AuditedColumns, Base):
    """Organisation sous-traitante : donnée du donneur d'ordre, sans donnée nominative ni compte externe."""

    __tablename__ = "subcontractor"
    __mapper_args__ = {"eager_defaults": True}

    subcontractor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    legal_name: Mapped[str] = mapped_column(String, nullable=False)
    registration_number: Mapped[str | None] = mapped_column(String)
    tax_id: Mapped[str | None] = mapped_column(String)
    country_code: Mapped[str] = mapped_column(String, nullable=False, server_default="GN")
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="ACTIVE")
    status_reason: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(String)
    # SLA contractuel (tranche 3) : objectif de disponibilité, comparé à la disponibilité MESURÉE.
    availability_target_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
