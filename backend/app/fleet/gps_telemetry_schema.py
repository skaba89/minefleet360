"""Schéma strict des coordonnées envoyées par un traceur GPS.

Aucun tenant, site, véhicule ou secret n'est accepté dans le corps JSON.
Le secret devra être transmis par un canal d'authentification séparé.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.fleet.gps_gateway_contract import GpsDeviceMessage


class GpsTelemetryIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    device_id: str = Field(min_length=1, max_length=120)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    recorded_at: datetime
    sequence: int = Field(ge=0, le=9223372036854775807)
    speed_kmh: float | None = Field(default=None, ge=0, le=250, allow_inf_nan=False)
    accuracy_m: float | None = Field(default=None, ge=0, le=10000, allow_inf_nan=False)

    @field_validator("device_id")
    @classmethod
    def valid_device_id(cls, value: str) -> str:
        if value != value.strip() or not value:
            raise ValueError("Invalid device identifier")
        return value

    @field_validator("recorded_at")
    @classmethod
    def aware_recorded_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timezone required")
        return value

    def to_message(self) -> GpsDeviceMessage:
        return GpsDeviceMessage(**self.model_dump())
