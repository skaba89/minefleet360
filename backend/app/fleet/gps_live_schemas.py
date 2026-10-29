import uuid
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, field_validator


class PhonePointIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False, strict=True)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False, strict=True)
    accuracy_m: float = Field(ge=0, le=10000, allow_inf_nan=False, strict=True)
    speed_kmh: float | None = Field(default=None, ge=0, le=250, allow_inf_nan=False, strict=True)
    recorded_at: AwareDatetime


class PhoneStartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vehicle_id: uuid.UUID
    consent: StrictBool

    @field_validator("consent")
    @classmethod
    def explicit_consent(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Le partage doit être explicitement accepté.")
        return value


class PhoneShareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    phone_share_id: uuid.UUID
    vehicle_id: uuid.UUID
    started_at: datetime
    expires_at: datetime
    stopped_at: datetime | None


class GpsVehicleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    vehicle_id: uuid.UUID
    site_id: uuid.UUID
    fleet_number: str
    registration_number: str | None


class TrackerCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


class TrackerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    gps_device_binding_id: uuid.UUID
    device_id: str
    active_from: datetime
    revoked_at: datetime | None


class TrackerProvisionOut(TrackerOut):
    token: str


class DriverAccountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_account_id: uuid.UUID | None


class DriverAccountOut(BaseModel):
    user_account_id: uuid.UUID | None
