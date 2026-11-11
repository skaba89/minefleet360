"""Schémas API du catalogue de plans SaaS (lot 1) et de la facturation (lot 3)."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.http import StrictModel

PLAN_CODE_PATTERN = r"^[A-Z][A-Z0-9_]{1,29}$"


class PlanCreate(StrictModel):
    code: str = Field(pattern=PLAN_CODE_PATTERN)
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    status: str = Field(default="DRAFT", pattern=r"^(DRAFT|ACTIVE)$")
    max_users: int | None = Field(default=None, ge=1, le=100_000)
    max_sites: int | None = Field(default=None, ge=1, le=10_000)
    max_vehicles: int | None = Field(default=None, ge=1, le=100_000)
    max_gps_trackers: int | None = Field(default=None, ge=1, le=100_000)
    document_retention_days: int | None = Field(default=None, ge=30, le=3650)
    # Lot 3 : tarif mensuel paramétrable en GNF (NULL = plan non tarifé) et période indicative.
    price_monthly_gnf: int | None = Field(default=None, ge=0)
    billing_period: str | None = Field(default=None, pattern=r"^(MONTHLY|ANNUAL)$")


class PlanUpdate(StrictModel):
    """PATCH partiel : seuls les champs fournis sont modifiés (le code est immuable)."""

    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default=None, pattern=r"^(DRAFT|ACTIVE|RETIRED)$")
    max_users: int | None = Field(default=None, ge=1, le=100_000)
    max_sites: int | None = Field(default=None, ge=1, le=10_000)
    max_vehicles: int | None = Field(default=None, ge=1, le=100_000)
    max_gps_trackers: int | None = Field(default=None, ge=1, le=100_000)
    document_retention_days: int | None = Field(default=None, ge=30, le=3650)
    price_monthly_gnf: int | None = Field(default=None, ge=0)
    billing_period: str | None = Field(default=None, pattern=r"^(MONTHLY|ANNUAL)$")


class PlanSummary(BaseModel):
    plan_id: uuid.UUID
    code: str
    name: str
    status: str
    max_users: int | None
    max_sites: int | None
    max_vehicles: int | None
    max_gps_trackers: int | None
    document_retention_days: int | None
    price_monthly_gnf: int | None
    billing_period: str | None
    row_version: int


class PlanOut(PlanSummary):
    description: str | None
    created_at: datetime
    updated_at: datetime


class SubscriptionCreate(StrictModel):
    """Création de l'abonnement courant d'une société : essai daté ou activation directe."""

    plan_id: uuid.UUID
    trial_days: int | None = Field(default=None, ge=1, le=365)
    period_ends_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=500)


class SubscriptionStatusChange(StrictModel):
    reason: str = Field(min_length=3, max_length=500)


class SubscriptionRenew(StrictModel):
    """Renouvellement de la période : la facture correspondante est émise via le lot 3."""

    period_ends_at: datetime


class SubscriptionSummary(BaseModel):
    subscription_id: uuid.UUID
    tenant_id: uuid.UUID
    plan_id: uuid.UUID
    plan_code: str
    plan_name: str
    status: str
    # Statut effectif calculé à la lecture (lot 3) : « EXPIRED » si l'essai daté est échu.
    effective_status: str
    trial_ends_at: datetime | None
    period_ends_at: datetime | None
    suspended_at: datetime | None
    cancelled_at: datetime | None
    suspension_reason: str | None
    row_version: int


class SubscriptionOut(SubscriptionSummary):
    notes: str | None
    created_at: datetime
    updated_at: datetime


class TenantSubscriptionOut(BaseModel):
    """Vue côté société : SON abonnement et les quotas du plan (aucune donnée commerciale interne)."""

    subscription_id: uuid.UUID
    status: str
    effective_status: str
    trial_ends_at: datetime | None
    period_ends_at: datetime | None
    plan: PlanSummary


# --- Facturation (lot 3) : document interne, sans encaissement applicatif -----------------------------


class InvoiceLineIn(StrictModel):
    description: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, le=100_000)
    unit_price_gnf: int = Field(ge=0)


class InvoiceCreate(StrictModel):
    """Création d'une facture DRAFT pour une société.

    Avec `subscription_id` et aucune ligne : une ligne est préremplie depuis le tarif du
    plan (422 PLAN_NOT_PRICED si le plan n'a pas de tarif). Sinon les lignes sont fournies.
    """

    subscription_id: uuid.UUID | None = None
    tax_rate_bp: int = Field(default=0, ge=0, le=10_000)
    period_start: date | None = None
    period_end: date | None = None
    notes: str | None = Field(default=None, max_length=500)
    lines: list[InvoiceLineIn] = Field(default_factory=list, max_length=50)


class InvoiceLineOut(BaseModel):
    line_id: uuid.UUID
    description: str
    quantity: int
    unit_price_gnf: int
    amount_gnf: int


class InvoiceSummary(BaseModel):
    invoice_id: uuid.UUID
    tenant_id: uuid.UUID
    subscription_id: uuid.UUID | None
    number: str
    status: str
    currency: str
    tax_rate_bp: int
    period_start: date | None
    period_end: date | None
    subtotal_gnf: int
    tax_gnf: int
    total_gnf: int
    row_version: int


class InvoiceOut(InvoiceSummary):
    issued_at: datetime | None
    voided_at: datetime | None
    void_reason: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    lines: list[InvoiceLineOut]


class InvoiceVoid(StrictModel):
    reason: str = Field(min_length=3, max_length=500)
