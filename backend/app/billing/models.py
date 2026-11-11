"""Catalogue de plans SaaS (lot 1), abonnements (lot 2) et facturation (lot 3) — commercialisation.

`saas_plan` est une donnée de référence PLATEFORME (aucun tenant_id, hors RLS applicative,
comme `tenant`) : elle décrit l'offre commerciale, les quotas et (lot 3) le tarif mensuel
paramétrable en GNF. `tenant_subscription` (lot 2) et `billing_invoice`/`billing_invoice_line`
(lot 3) sont des tables applicatives RLS classiques : la société lit SES lignes.
Aucun moyen de paiement : la facture (DRAFT → ISSUED → VOIDED) est un document interne
de traçabilité, le règlement se gère hors application tant que le paiement n'est pas approuvé.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, text
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
        CheckConstraint("price_monthly_gnf IS NULL OR price_monthly_gnf >= 0", name="ck_saas_plan_price"),
        CheckConstraint(
            "billing_period IS NULL OR billing_period IN ('MONTHLY', 'ANNUAL')", name="ck_saas_plan_period"
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
    # Lot 3 : tarif mensuel paramétrable en GNF (NULL = plan non tarifé), période indicative.
    price_monthly_gnf: Mapped[int | None] = mapped_column(BigInteger)
    billing_period: Mapped[str | None] = mapped_column(String)


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


class BillingInvoice(AuditedColumns, Base):
    """Facture interne d'une société (lot 3) — traçabilité, sans encaissement applicatif.

    Cycle DRAFT → ISSUED → VOIDED (terminal). Numérotation plateforme lisible
    (`MF-<année>-<numéro>`), montants en GNF figés à la création (subtotal, taxe en
    points de base, total), lignes immuables dans `billing_invoice_line`.
    """

    __tablename__ = "billing_invoice"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'ISSUED', 'VOIDED')", name="ck_bi_status"),
        CheckConstraint("currency = 'GNF'", name="ck_bi_currency"),
        CheckConstraint("tax_rate_bp BETWEEN 0 AND 10000", name="ck_bi_tax"),
    )
    __mapper_args__ = {"eager_defaults": True}

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False, index=True
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant_subscription.subscription_id")
    )
    number: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="DRAFT")
    currency: Mapped[str] = mapped_column(String, nullable=False, server_default="GNF")
    tax_rate_bp: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    subtotal_gnf: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    tax_gnf: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    total_gnf: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(String)


class BillingInvoiceLine(Base):
    """Ligne de facture immuable : montant = quantité × prix unitaire (contrainte en base)."""

    __tablename__ = "billing_invoice_line"
    __table_args__ = (
        CheckConstraint("quantity BETWEEN 1 AND 100000", name="ck_bil_quantity"),
        CheckConstraint("unit_price_gnf >= 0", name="ck_bil_unit_price"),
    )
    __mapper_args__ = {"eager_defaults": True}

    line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_invoice.invoice_id"), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.tenant_id"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_gnf: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_gnf: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class BillingInvoiceSequence(Base):
    """Compteur de numérotation des factures par année (table plateforme, hors RLS)."""

    __tablename__ = "billing_invoice_sequence"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
