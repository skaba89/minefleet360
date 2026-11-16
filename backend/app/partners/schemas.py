import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.http import StrictModel

SubcontractorStatus = Literal["ACTIVE", "SUSPENDED", "ENDED"]


class SubcontractorCreate(StrictModel):
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    legal_name: str = Field(min_length=1, max_length=240)
    registration_number: str | None = Field(default=None, min_length=1, max_length=64)
    tax_id: str | None = Field(default=None, min_length=1, max_length=64)
    country_code: str = Field(default="GN", pattern=r"^[A-Z]{2}$")
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _not_blank(self) -> "SubcontractorCreate":
        if not self.legal_name.strip():
            raise ValueError("legal_name vide")
        return self


class SubcontractorUpdate(StrictModel):
    legal_name: str | None = Field(default=None, min_length=1, max_length=240)
    registration_number: str | None = Field(default=None, min_length=1, max_length=64)
    tax_id: str | None = Field(default=None, min_length=1, max_length=64)
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    notes: str | None = Field(default=None, max_length=2000)
    status: SubcontractorStatus | None = None
    # Obligatoire pour SUSPENDED/ENDED, interdit pour ACTIVE (contrainte ck_subcontractor_reason).
    status_reason: str | None = Field(default=None, min_length=3, max_length=500)

    @model_validator(mode="after")
    def _reason_matches_status(self) -> "SubcontractorUpdate":
        if self.status in ("SUSPENDED", "ENDED") and not (self.status_reason or "").strip():
            raise ValueError("status_reason requis pour une suspension ou une fin de relation")
        if self.status == "ACTIVE" and self.status_reason is not None:
            raise ValueError("status_reason interdit pour une réactivation")
        if self.status is None and self.status_reason is not None:
            raise ValueError("status_reason sans changement de statut")
        return self


class SubcontractorOut(BaseModel):
    subcontractor_id: uuid.UUID
    code: str
    legal_name: str
    registration_number: str | None
    tax_id: str | None
    country_code: str
    status: SubcontractorStatus
    status_reason: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    row_version: int
