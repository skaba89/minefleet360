"""Validation stricte des commandes de plans préventifs (sans écriture en base)."""

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.core.http import StrictModel


class PreventivePlanCreate(StrictModel):
    vehicle_id: uuid.UUID
    code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    km_interval: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=1)
    hours_interval: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=1)
    days_interval: int | None = Field(default=None, gt=0, le=36500)

    @field_validator("km_interval", "hours_interval")
    @classmethod
    def finite_meter(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("le seuil doit être fini")
        return value

    @model_validator(mode="after")
    def require_threshold(self) -> "PreventivePlanCreate":
        if all(value is None for value in (self.km_interval, self.hours_interval, self.days_interval)):
            raise ValueError("au moins une périodicité est requise")
        return self


class PreventivePlanSuspend(StrictModel):
    reason: str = Field(min_length=3, max_length=300)


class ServiceDeclarationCreate(StrictModel):
    """Dernier entretien connu d'un engin et d'un code de plan (ou « inconnu »), à faire approuver."""

    vehicle_id: uuid.UUID
    plan_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    knowledge: Literal["KNOWN", "UNKNOWN"]
    serviced_at: AwareDatetime | None = None
    odometer_km: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=1)
    hour_meter: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=1)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("odometer_km", "hour_meter")
    @classmethod
    def finite_meter(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("le compteur doit être fini")
        return value

    @model_validator(mode="after")
    def consistent(self) -> "ServiceDeclarationCreate":
        if self.knowledge == "KNOWN" and self.serviced_at is None:
            raise ValueError("la date du dernier entretien est requise")
        if self.knowledge == "UNKNOWN" and any(
            v is not None for v in (self.serviced_at, self.odometer_km, self.hour_meter)
        ):
            raise ValueError("un entretien inconnu ne porte ni date ni compteur")
        return self


class ServiceDeclarationDecide(StrictModel):
    decision: Literal["APPROVE", "REJECT"]
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def rejection_reason(self) -> "ServiceDeclarationDecide":
        if self.decision == "REJECT" and not (self.note or "").strip():
            raise ValueError("le motif du rejet est requis")
        return self
