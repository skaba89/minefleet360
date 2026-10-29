"""Contrat strict des positions GPS entrantes, indépendant du fournisseur.

Aucune ingestion HTTP, authentification d'équipement ou persistance n'est
implémentée ici. Les contrôles précèdent toute promotion d'une position.
"""

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class GpsPosition:
    vehicle_id: uuid.UUID
    device_id: str
    latitude: float
    longitude: float
    recorded_at: datetime
    speed_kmh: float | None = None
    accuracy_m: float | None = None


def valid_gps_position(position: GpsPosition, *, received_at: datetime) -> bool:
    """Rejeter les points impossibles, futurs ou trop anciens (24 heures)."""
    if position.vehicle_id.int == 0 or not position.device_id.strip():
        return False
    if position.recorded_at.tzinfo is None or received_at.tzinfo is None:
        return False
    recorded = position.recorded_at.astimezone(UTC)
    received = received_at.astimezone(UTC)
    if recorded > received + timedelta(minutes=2) or recorded < received - timedelta(hours=24):
        return False
    if not (math.isfinite(position.latitude) and -90 <= position.latitude <= 90):
        return False
    if not (math.isfinite(position.longitude) and -180 <= position.longitude <= 180):
        return False
    if position.speed_kmh is not None and (
        not math.isfinite(position.speed_kmh) or not 0 <= position.speed_kmh <= 250
    ):
        return False
    if position.accuracy_m is not None and (
        not math.isfinite(position.accuracy_m) or not 0 <= position.accuracy_m <= 10000
    ):
        return False
    return True
