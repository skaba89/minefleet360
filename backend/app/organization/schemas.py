import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.http import StrictModel
from app.core.timezones import is_valid_timezone

SiteType = Literal["MINE", "QUARRY", "WORKSHOP", "DEPOT", "PORT", "OFFICE"]


def _check_timezone(value: str | None) -> str | None:
    if value is not None and not is_valid_timezone(value):
        raise ValueError("fuseau horaire IANA inconnu")
    return value


class TenantCreate(StrictModel):
    code: str = Field(pattern=r"^[a-z0-9-]{3,32}$")
    legal_name: str = Field(min_length=2, max_length=200)
    display_name: str = Field(min_length=2, max_length=100)
    default_timezone: str = "Africa/Conakry"
    admin_email: EmailStr
    admin_display_name: str = Field(min_length=2, max_length=100)

    _tz = field_validator("default_timezone")(_check_timezone)


class TenantStatusChange(StrictModel):
    reason: str = Field(min_length=3, max_length=500)


class TenantSummary(BaseModel):
    """Métadonnées de gestion visibles par PLATFORM_ADMIN (jamais de donnée métier)."""

    tenant_id: uuid.UUID
    code: str
    display_name: str
    status: str
    is_demo: bool
    created_at: datetime
    row_version: int


class TenantOut(BaseModel):
    tenant_id: uuid.UUID
    code: str
    legal_name: str
    display_name: str
    status: str
    default_timezone: str
    default_locale: str
    currency_code: str
    row_version: int


class TenantUpdate(StrictModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=100)
    default_timezone: str | None = None

    _tz = field_validator("default_timezone")(_check_timezone)


class SiteCreate(StrictModel):
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    name: str = Field(min_length=2, max_length=120)
    site_type: SiteType
    timezone: str | None = None

    _tz = field_validator("timezone")(_check_timezone)


class SiteUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    site_type: SiteType | None = None
    timezone: str | None = None

    _tz = field_validator("timezone")(_check_timezone)


class SiteOut(BaseModel):
    site_id: uuid.UUID
    code: str
    name: str
    site_type: str
    timezone: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    row_version: int
