"""Catalogue de plans SaaS (lot 1) et abonnements (lot 2) — commercialisation.

`saas_plan` est une donnée de référence PLATEFORME (aucun tenant_id, hors RLS applicative,
comme `tenant`) : elle décrit l'offre commerciale et les quotas associés. `tenant_subscription`
(lot 2) est une table applicative RLS classique : la société lit SON abonnement.
Aucune colonne de prix : conformément à la règle « pas d'intégration de paiement
ni de tarif non approuvé », la tarification n'est PAS modélisée avant arbitrage métier.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import AuditedColumns


class SaaSPlan(AuditedColumns, Base):
    __tablename__ = "saas_plan"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'RETIRED')", name="ck_saas_plan_status"),
        CheckConstraint(
            "(max_users IS NULL OR max_users BETWEEN 1 AND 100000)"
            " AND (max_sites IS NULL OR max_sites BETWEEN 1 AND 10000)"
            " AND (max_vehicles IS NULL OR max_vehicles BETWEEN 1 AND 100000)"
            " AND (max_gps_trackers IS NULL OR max_gps_trackers BETWEEN 1 AND 100000)"
            " AND (document_retention_days IS NULL OR document_retention_days BETWEEN 30 AND 3650)",
            name="ck_saas_plan_quotas",
        ),
    )
    __mapper_args__ = {"eager_defaults": True}

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="DRAFT")
    # Quotas : NULL = illimité (documenté dans LIVRAISON_SAAS_PLANS.md).
    max_users: Mapped[int | None] = mapped_column(Integer)
    max_sites: Mapped[int | None] = mapped_column(Integer)
    max_vehicles: Mapped[int | None] = mapped_column(Integer)
    max_gps_trackers: Mapped[int | None] = mapped_column(Integer)
    document_retention_days: Mapped[int | None] = mapped_column(Integer)


class TenantSubscription(AuditedColumns, Base):
    """Abonnement d'une société à un plan (un abonnement « vivant » à la fois par société).

    Cycle : TRIAL → ACTIVE → SUSPENDED (↔ réactivation) ; CANCELLED terminal.
    La table est soumise à la RLS applicative : chaque société ne voit que ses lignes.
    """

    __tablename__ = "tenant_subscription"
    __table_args__ = (
        CheckConstraint("status IN ('TRIAL', 'ACTIVE', 'SUSPENDED', 'CANCELLED')", name="ck_ts_status"),
    )
    __mapper_args__ = {"eager_defaults": True}

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False, index=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("saas_plan.plan_id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="TRIAL")
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspension_reason: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(String)
