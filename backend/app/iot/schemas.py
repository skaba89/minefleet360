"""Registry contracts; tenant, status and sensor provenance are server-owned."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.http import StrictModel

Label = Annotated[str, Field(min_length=1, max_length=120)]
SourceKind = Literal["SIMULATED", "PHYSICAL"]
SensorKind = Literal["TPMS", "HUB_TEMPERATURE", "WHEEL_LOOSENING", "COMBINED"]
RegistryStatus = Literal["REGISTERED", "RETIRED"]


class ManufacturerCreate(StrictModel):
    name: Label


class GatewayCreate(StrictModel):
    site_id: uuid.UUID
    manufacturer_id: uuid.UUID
    external_id: Label
    model: Label
    source_kind: SourceKind


class SensorCreate(StrictModel):
    gateway_id: uuid.UUID
    manufacturer_id: uuid.UUID
    external_id: Label
    model: Label
    sensor_kind: SensorKind


class ManufacturerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    manufacturer_id: uuid.UUID
    name: str
    created_at: datetime


class GatewayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    gateway_id: uuid.UUID
    site_id: uuid.UUID
    manufacturer_id: uuid.UUID
    external_id: str
    model: str
    source_kind: SourceKind
    status: RegistryStatus
    created_at: datetime


class SensorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sensor_id: uuid.UUID
    site_id: uuid.UUID
    gateway_id: uuid.UUID
    manufacturer_id: uuid.UUID
    external_id: str
    model: str
    source_kind: SourceKind
    sensor_kind: SensorKind
    status: RegistryStatus
    created_at: datetime
