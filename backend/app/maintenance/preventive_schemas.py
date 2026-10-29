"""Contrats publics limités de la maintenance préventive."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.http import StrictModel


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


class PreventiveScheduledOrderOut(BaseModel):
    work_order_id: uuid.UUID


class PreventiveCompletionIn(StrictModel):
    odometer_approval_id: uuid.UUID | None = None
    hour_meter_approval_id: uuid.UUID | None = None


class PreventiveCompletionOut(BaseModel):
    work_order_id: uuid.UUID
    status: Literal["COMPLETED"]
    changed: bool


class PreventiveApprovalChoiceOut(BaseModel):
    approval_id: uuid.UUID
    cumulative_total: Decimal
    approved_at: datetime


class PreventiveCompletionMeterOut(BaseModel):
    meter_kind: Literal["ODOMETER_KM", "HOUR_METER"]
    frozen_total: Decimal | None = None
    approvals: list[PreventiveApprovalChoiceOut]


class PreventiveCompletionContextOut(BaseModel):
    maintenance_due_id: uuid.UUID
    status: Literal["SCHEDULED", "COMPLETED"]
    plan_code: str
    closed_at: datetime
    meters: list[PreventiveCompletionMeterOut]
