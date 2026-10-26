import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.http import StrictModel

VehicleStatus = Literal["AVAILABLE", "IN_MAINTENANCE", "IMMOBILIZED", "OUT_OF_SERVICE", "RETIRED"]
OperationalStatus = Literal["AVAILABLE", "IN_MAINTENANCE", "IMMOBILIZED", "OUT_OF_SERVICE"]
Ownership = Literal["OWNED", "LEASED", "SUBCONTRACTED"]
FuelType = Literal["DIESEL", "PETROL", "ELECTRIC", "OTHER"]
# Codes de motif (pas de texte libre : pas de donnée personnelle dans un motif).
ReasonCode = Literal[
    "BREAKDOWN",
    "ACCIDENT",
    "DOCUMENT_EXPIRED",
    "AWAITING_PARTS",
    "SAFETY_BAN",
    "PREVENTIVE_MAINTENANCE",
    "RECEPTION_IN_PROGRESS",
    "END_OF_LIFE",
    "TOTAL_LOSS",
    "SOLD",
    "OTHER",
]


class VehicleCategoryOut(BaseModel):
    vehicle_category_id: uuid.UUID
    code: str
    label_fr: str
    family: str
    requires_driver: bool
    requires_internal_authorization: bool
    has_odometer: bool
    has_hour_meter: bool
    is_active: bool
    required_license_categories: list[str]


class VehicleCreate(StrictModel):
    site_id: uuid.UUID
    vehicle_category_id: uuid.UUID
    fleet_number: str = Field(pattern=r"^\S{1,30}$")
    registration_number: str | None = Field(default=None, min_length=2, max_length=20)
    serial_number: str | None = Field(default=None, min_length=1, max_length=60)
    make: str | None = Field(default=None, max_length=60)
    model: str | None = Field(default=None, max_length=60)
    model_year: int | None = Field(default=None, ge=1950, le=2100)
    ownership_type: Ownership = "OWNED"
    fuel_type: FuelType | None = None
    rated_payload_kg: int | None = Field(default=None, gt=0, le=1_000_000)
    commissioned_on: date | None = None
    notes: str | None = Field(default=None, max_length=1000)


class VehicleUpdate(StrictModel):
    site_id: uuid.UUID | None = None
    vehicle_category_id: uuid.UUID | None = None
    registration_number: str | None = Field(default=None, min_length=2, max_length=20)
    serial_number: str | None = Field(default=None, min_length=1, max_length=60)
    make: str | None = Field(default=None, max_length=60)
    model: str | None = Field(default=None, max_length=60)
    model_year: int | None = Field(default=None, ge=1950, le=2100)
    ownership_type: Ownership | None = None
    fuel_type: FuelType | None = None
    rated_payload_kg: int | None = Field(default=None, gt=0, le=1_000_000)
    commissioned_on: date | None = None
    notes: str | None = Field(default=None, max_length=1000)


class VehicleStatusChange(StrictModel):
    status: OperationalStatus
    reason_code: ReasonCode | None = None


class VehicleRetire(StrictModel):
    reason_code: ReasonCode


class VehicleOut(BaseModel):
    vehicle_id: uuid.UUID
    site_id: uuid.UUID
    vehicle_category_id: uuid.UUID
    fleet_number: str
    registration_number: str | None
    serial_number: str | None
    make: str | None
    model: str | None
    model_year: int | None
    ownership_type: str
    fuel_type: str | None
    rated_payload_kg: int | None
    status: str
    status_reason_code: str | None
    status_changed_at: datetime
    commissioned_on: date | None
    decommissioned_on: date | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    row_version: int


class StatusHistoryOut(BaseModel):
    from_status: str | None
    to_status: str
    reason_code: str | None
    changed_at: datetime
    changed_by: uuid.UUID | None
