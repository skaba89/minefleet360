"""Prévalidation GPS sous une identité de passerelle déjà authentifiée.

Ne crée pas de point, et n'expose pas d'API publique. Les propriétés du
véhicule proviennent de la liaison persistée, jamais du corps du traceur.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.fleet.gps_binding_lookup import resolve_gps_binding
from app.fleet.gps_contract import GpsPosition, valid_gps_position
from app.fleet.gps_credential_verify import verify_persisted_gps_credential


def preflight_gps_ingestion(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    position: GpsPosition,
    supplied_secret: str,
    received_at: datetime,
) -> bool:
    """Exiger coordonnées valides, liaison active et secret non révoqué."""
    if tenant_id.int == 0 or site_id.int == 0:
        return False
    if not valid_gps_position(position, received_at=received_at):
        return False
    binding = resolve_gps_binding(
        db,
        tenant_id=tenant_id,
        vehicle_id=position.vehicle_id,
        site_id=site_id,
        device_id=position.device_id,
        recorded_at=received_at,
    )
    if binding is None:
        return False
    if binding.revoked_at is not None:
        return False
    return verify_persisted_gps_credential(
        db,
        tenant_id=tenant_id,
        binding_id=binding.gps_device_binding_id,
        supplied_secret=supplied_secret,
        at=received_at,
    )
