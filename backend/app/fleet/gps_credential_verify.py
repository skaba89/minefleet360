"""Vérification interne d'un secret GPS persisté, sous contexte tenant RLS.

Le tenant et l'association viennent d'une passerelle authentifiée. Cette
fonction n'est pas un endpoint de réception et ne crée aucune position.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fleet.gps_credential_models import FleetGpsDeviceCredential
from app.fleet.gps_device_credentials import verify_device_secret


def verify_persisted_gps_credential(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    binding_id: uuid.UUID,
    supplied_secret: str,
    at: datetime,
) -> bool:
    """Rejeter tout secret absent, périmé, révoqué ou de mauvaise association."""
    if tenant_id.int == 0 or binding_id.int == 0 or at.tzinfo is None:
        return False
    if not isinstance(supplied_secret, str) or not 32 <= len(supplied_secret) <= 256:
        return False
    credential = db.execute(
        select(FleetGpsDeviceCredential).where(
            FleetGpsDeviceCredential.tenant_id == tenant_id,
            FleetGpsDeviceCredential.gps_device_binding_id == binding_id,
            FleetGpsDeviceCredential.active_from <= at,
            FleetGpsDeviceCredential.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    if credential is None:
        return False
    return verify_device_secret(credential.secret_fingerprint, supplied_secret)
