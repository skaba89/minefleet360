"""Réponse GPS de supervision : jamais de coordonnées qualifiées de live sans fraîcheur."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GpsLatestPositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    vehicle_id: uuid.UUID
    site_id: uuid.UUID
    latitude: float
    longitude: float
    speed_kmh: float | None
    accuracy_m: float | None
    recorded_at: datetime
    received_at: datetime
    source: str = "TRACKER"
    source_active: bool = True
