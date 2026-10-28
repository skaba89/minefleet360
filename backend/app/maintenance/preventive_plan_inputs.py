"""Validation stricte des commandes de plans préventifs (sans écriture en base)."""

import uuid
from decimal import Decimal

from pydantic import Field, field_validator, model_validator

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
        if all(
            value is None
            for value in (self.km_interval, self.hours_interval, self.days_interval)
        ):
            raise ValueError("au moins une périodicité est requise")
        return self


class PreventivePlanSuspend(StrictModel):
    reason: str = Field(min_length=3, max_length=300)
