"""Schémas API du catalogue de plans SaaS (lot 1)."""

import uuid
from datetime import datetime

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
    """Renouvellement manuel de la période (lot 3 apportera la facturation)."""

    period_ends_at: datetime


class SubscriptionSummary(BaseModel):
    subscription_id: uuid.UUID
    tenant_id: uuid.UUID
    plan_id: uuid.UUID
    plan_code: str
    plan_name: str
    status: str
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
    trial_ends_at: datetime | None
    period_ends_at: datetime | None
    plan: PlanSummary
