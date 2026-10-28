"""Réponses publiques limitées des plans et échéances de maintenance préventive."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class PreventivePlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    maintenance_plan_id: uuid.UUID
    vehicle_id: uuid.UUID
    code: str
    version: int
    km_interval: Decimal | None
    hours_interval: Decimal | None
    days_interval: int | None
    active: bool
    suspension_reason: str | None
    row_version: int


class PreventiveDueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    maintenance_due_id: uuid.UUID
    maintenance_plan_id: uuid.UUID
    vehicle_id: uuid.UUID
    trigger_kind: Literal["KM", "HOURS", "DAYS"]
    status: Literal["DUE", "SCHEDULED", "COMPLETED", "CANCELLED"]
    due_on: date | None
    due_meter: Decimal | None
    evaluated_at: datetime
    work_order_id: uuid.UUID | None
