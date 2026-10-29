"""Contrat du message GPS reçu via une passerelle authentifiée.

La charge utile du traceur ne porte ni tenant_id, ni site_id, ni vehicle_id.
L'identité du camion est exclusivement issue de l'association persistée.
Ce contrat ne constitue pas une authentification HTTP.
"""

import math
import uuid
from dataclasses import dataclass
from datetime import datetime

from app.fleet.gps_contract import GpsPosition


@dataclass(frozen=True)
class TrustedGpsBinding:
    """Identité résolue côté serveur après authentification du traceur."""

    tenant_id: uuid.UUID
    site_id: uuid.UUID
    vehicle_id: uuid.UUID
    device_id: str


@dataclass(frozen=True)
class GpsDeviceMessage:
    """Valeurs déclarées par un équipement, jamais une identité de tenant."""

    device_id: str
    latitude: float
    longitude: float
    recorded_at: datetime
    sequence: int
    speed_kmh: float | None = None
    accuracy_m: float | None = None


def position_from_trusted_binding(
    binding: TrustedGpsBinding, message: GpsDeviceMessage
) -> GpsPosition | None:
    """Construire la position uniquement depuis une identité serveur cohérente."""
    if (
        binding.tenant_id.int == 0
        or binding.site_id.int == 0
        or binding.vehicle_id.int == 0
        or not binding.device_id
        or message.device_id != binding.device_id
    ):
        return None
    if isinstance(message.sequence, bool) or not isinstance(message.sequence, int):
        return None
    if not 0 <= message.sequence <= 9223372036854775807:
        return None
    if message.recorded_at.tzinfo is None:
        return None
    if not (math.isfinite(message.latitude) and math.isfinite(message.longitude)):
        return None
    return GpsPosition(
        vehicle_id=binding.vehicle_id,
        device_id=binding.device_id,
        latitude=message.latitude,
        longitude=message.longitude,
        recorded_at=message.recorded_at,
        speed_kmh=message.speed_kmh,
        accuracy_m=message.accuracy_m,
    )
