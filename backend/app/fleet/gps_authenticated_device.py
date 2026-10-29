"""Résolution d'une identité GPS à partir d'un secret et d'un tenant fiable.

Le tenant provient exclusivement de la passerelle préalablement authentifiée.
Aucun tenant n'est déduit d'une entrée non fiable et aucune route n'est exposée.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fleet.gps_binding_models import FleetGpsDeviceBinding
from app.fleet.gps_credential_models import FleetGpsDeviceCredential
from app.fleet.gps_device_credentials import verify_device_secret
from app.fleet.gps_gateway_contract import TrustedGpsBinding


def resolve_authenticated_gps_device(
    db: Session,
    *,
    trusted_tenant_id: uuid.UUID,
    device_id: str,
    supplied_secret: str,
    at: datetime,
) -> TrustedGpsBinding | None:
    """Vérifier liaison et secret actifs, puis produire l'identité côté serveur."""
    if trusted_tenant_id.int == 0 or not device_id or not device_id.strip():
        return None
    if at.tzinfo is None or at.utcoffset() is None:
        return None
    if not isinstance(supplied_secret, str) or not 32 <= len(supplied_secret) <= 256:
        return None

    statement = (
        select(FleetGpsDeviceBinding, FleetGpsDeviceCredential.secret_fingerprint)
        .join(
            FleetGpsDeviceCredential,
            (FleetGpsDeviceCredential.tenant_id == FleetGpsDeviceBinding.tenant_id)
            & (
                FleetGpsDeviceCredential.gps_device_binding_id
                == FleetGpsDeviceBinding.gps_device_binding_id
            ),
        )
        .where(
            FleetGpsDeviceBinding.tenant_id == trusted_tenant_id,
            FleetGpsDeviceBinding.device_id == device_id,
            FleetGpsDeviceBinding.active_from <= at,
            FleetGpsDeviceBinding.revoked_at.is_(None),
            FleetGpsDeviceCredential.active_from <= at,
            FleetGpsDeviceCredential.revoked_at.is_(None),
        )
    )
    row = db.execute(statement).one_or_none()
    if row is None:
        return None
    binding, fingerprint = row
    if not verify_device_secret(fingerprint, supplied_secret):
        return None
    return TrustedGpsBinding(
        tenant_id=binding.tenant_id,
        site_id=binding.site_id,
        vehicle_id=binding.vehicle_id,
        device_id=binding.device_id,
    )
