import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.core.http import StrictModel

FuelType = Literal["DIESEL", "PETROL"]
MeterKind = Literal["ODOMETER", "HOUR_METER"]
Decision = Literal["APPROVED", "REJECTED"]
RejectReason = Literal["WRONG_VEHICLE", "INVALID_QUANTITY", "OTHER"]
StocktakeReason = Literal["MEASUREMENT", "LOSS", "DATA_CORRECTION", "OTHER"]


class TankCreate(StrictModel):
    site_id: uuid.UUID
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    fuel_type: FuelType
    capacity_liters: Decimal = Field(gt=0, le=2_000_000, max_digits=12, decimal_places=3)
    low_stock_threshold_liters: Decimal | None = Field(
        default=None, gt=0, le=2_000_000, max_digits=12, decimal_places=3
    )

    @model_validator(mode="after")
    def threshold_within_capacity(self) -> "TankCreate":
        if (
            self.low_stock_threshold_liters is not None
            and self.low_stock_threshold_liters > self.capacity_liters
        ):
            raise ValueError("Le seuil d'alerte ne peut pas dépasser la capacité de la cuve.")
        return self


class ThresholdUpdate(StrictModel):
    low_stock_threshold_liters: Decimal | None = Field(
        default=None, gt=0, le=2_000_000, max_digits=12, decimal_places=3
    )


class ReceiptCreate(StrictModel):
    liters: Decimal = Field(gt=0, le=2_000_000, max_digits=12, decimal_places=3)
    reference: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9/_ .-]{1,60}$")
    occurred_at: AwareDatetime


class StocktakeCreate(StrictModel):
    counted_liters: Decimal = Field(ge=0, le=2_000_000, max_digits=12, decimal_places=3)
    reference: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9/_ .-]{1,60}$")
    reason_code: StocktakeReason
    occurred_at: AwareDatetime


class IssueCreate(StrictModel):
    fuel_tank_id: uuid.UUID
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID
    liters: Decimal = Field(gt=0, le=100_000, max_digits=12, decimal_places=3)
    meter_kind: MeterKind | None = None
    meter_value: Decimal | None = Field(default=None, ge=0, le=999_999_999, max_digits=12, decimal_places=1)
    full_tank: bool = False
    requested_at: AwareDatetime

    @model_validator(mode="after")
    def full_tank_requires_meter(self) -> "IssueCreate":
        if self.full_tank and (self.meter_kind is None or self.meter_value is None):
            raise ValueError("Un plein complet exige un relevé de compteur.")
        return self


class DecisionCreate(StrictModel):
    decision: Decision
    reason_code: RejectReason | None = None

    @model_validator(mode="after")
    def reason_matches_decision(self) -> "DecisionCreate":
        if (self.decision == "REJECTED") != (self.reason_code is not None):
            raise ValueError("Un refus exige un motif et une approbation n'en accepte pas.")
        return self


class TankOut(BaseModel):
    fuel_tank_id: uuid.UUID
    site_id: uuid.UUID
    code: str
    fuel_type: FuelType
    capacity_liters: Decimal
    low_stock_threshold_liters: Decimal | None
    low_stock: bool
    balance_liters: Decimal
    reserved_liters: Decimal
    available_liters: Decimal


class FuelIssueOut(BaseModel):
    fuel_issue_id: uuid.UUID
    site_id: uuid.UUID
    fuel_tank_id: uuid.UUID
    tank_code: str
    fuel_type: FuelType
    vehicle_id: uuid.UUID
    vehicle_fleet_number: str
    driver_id: uuid.UUID
    liters: Decimal
    meter_kind: MeterKind | None
    meter_value: Decimal | None
    full_tank: bool
    requested_at: datetime
    requested_by: uuid.UUID
    status: Literal["PENDING_APPROVAL", "APPROVED", "REJECTED"]
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    reason_code: str | None


class FuelReceiptOut(BaseModel):
    fuel_stock_movement_id: uuid.UUID
    site_id: uuid.UUID
    fuel_tank_id: uuid.UUID
    liters: Decimal
    reference: str
    occurred_at: datetime
    recorded_by: uuid.UUID
    recorded_at: datetime


class FuelStocktakeOut(BaseModel):
    fuel_stocktake_id: uuid.UUID
    site_id: uuid.UUID
    fuel_tank_id: uuid.UUID
    tank_code: str
    expected_liters: Decimal
    counted_liters: Decimal
    delta_liters: Decimal
    reference: str
    reason_code: StocktakeReason
    occurred_at: datetime
    recorded_by: uuid.UUID
    recorded_at: datetime


class FuelStockAlertOut(BaseModel):
    fuel_stock_alert_id: uuid.UUID
    site_id: uuid.UUID
    fuel_tank_id: uuid.UUID
    tank_code: str
    fuel_type: FuelType
    threshold_liters: Decimal
    balance_liters: Decimal
    triggered_at: datetime
    acknowledged_by: uuid.UUID | None
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    resolution_balance_liters: Decimal | None


class FuelConsumptionOut(BaseModel):
    fuel_issue_id: uuid.UUID
    vehicle_id: uuid.UUID
    vehicle_fleet_number: str
    site_id: uuid.UUID
    fuel_type: FuelType
    meter_kind: MeterKind
    interval_start_at: datetime
    interval_end_at: datetime
    start_meter_value: Decimal
    end_meter_value: Decimal
    meter_delta: Decimal
    fuel_liters: Decimal
    rate_liters_per_unit: Decimal
    comparison_median_rate: Decimal | None
    comparison_interval_count: int
    is_anomaly: bool
