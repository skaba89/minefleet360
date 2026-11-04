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
    trigger_kind: Literal["KM", "HOURS", "DAYS", "INITIAL"]
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


class ServiceDeclarationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service_declaration_id: uuid.UUID
    vehicle_id: uuid.UUID
    site_id: uuid.UUID
    plan_code: str
    knowledge: Literal["KNOWN", "UNKNOWN"]
    serviced_at: datetime | None
    odometer_km: Decimal | None
    hour_meter: Decimal | None
    note: str | None
    status: Literal["PENDING", "APPROVED", "REJECTED"]
    declared_by: uuid.UUID
    declared_at: datetime
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    decision_note: str | None


class PreventivePlanStatusOut(BaseModel):
    """État calculé d'un plan actif à l'instant de la lecture (aucune échéance enregistrée)."""

    maintenance_plan_id: uuid.UUID
    code: str
    status: Literal["DUE", "UPCOMING", "INSUFFICIENT_DATA", "NOT_CONFIGURED"]
    due_triggers: list[Literal["KM", "HOURS", "DAYS", "INITIAL"]]
    unknown_triggers: list[Literal["KM", "HOURS", "DAYS", "INITIAL"]]
    baseline_source: Literal["WORK_ORDER", "DECLARATION", "INITIAL_REQUIRED", "NONE"]
    serviced_on: date | None
    due_on: date | None
    current_km: Decimal | None
    current_hours: Decimal | None
    remaining_km: Decimal | None
    remaining_hours: Decimal | None
    km_reliable: bool
    hours_reliable: bool


class PreventiveEvaluateIn(StrictModel):
    site_id: uuid.UUID | None = None


class PreventiveEvaluationOut(BaseModel):
    plans_evaluated: int
    due_now: int
    created: int
    already_recorded: int
    upcoming: int
    insufficient_data: int


class SiteDueOut(BaseModel):
    maintenance_due_id: uuid.UUID
    maintenance_plan_id: uuid.UUID
    plan_code: str
    vehicle_id: uuid.UUID
    fleet_number: str
    site_id: uuid.UUID
    trigger_kind: Literal["KM", "HOURS", "DAYS", "INITIAL"]
    status: Literal["DUE", "SCHEDULED", "COMPLETED", "CANCELLED"]
    due_on: date | None
    due_meter: Decimal | None
    evaluated_at: datetime
    work_order_id: uuid.UUID | None
