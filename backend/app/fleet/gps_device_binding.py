"""Contrat de rattachement GPS : refuser les identités d'appareil ambiguës.

Validation pure. Le contrôle des secrets, la révocation et la persistance
du rattachement restent à implémenter avant toute ingestion HTTP.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class GpsDeviceBinding:
    tenant_id: uuid.UUID
    vehicle_id: uuid.UUID
    site_id: uuid.UUID
    device_id: str
    active_from: datetime
    revoked_at: datetime | None = None


def device_matches_binding(
    binding: GpsDeviceBinding,
    *,
    tenant_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    site_id: uuid.UUID,
    device_id: str,
    recorded_at: datetime,
) -> bool:
    """Accepter uniquement une identité liée, active à l'heure du point."""
    if any(value.int == 0 for value in (tenant_id, vehicle_id, site_id)):
        return False
    if (
        binding.tenant_id != tenant_id
        or binding.vehicle_id != vehicle_id
        or binding.site_id != site_id
    ):
        return False
    if not device_id or device_id.strip() != device_id or binding.device_id != device_id:
        return False
    if binding.active_from.tzinfo is None or recorded_at.tzinfo is None:
        return False
    if recorded_at.astimezone(UTC) < binding.active_from.astimezone(UTC):
        return False
    revoked_at = binding.revoked_at
    if revoked_at is not None:
        if revoked_at.tzinfo is None or recorded_at.astimezone(UTC) >= revoked_at.astimezone(UTC):
            return False
    return True
