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
