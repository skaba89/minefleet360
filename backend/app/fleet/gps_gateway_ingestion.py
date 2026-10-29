"""Chaîne GPS interne reliant un contexte tenant fiable au stockage atomique.

La provenance du tenant doit être authentifiée par la passerelle appelante.
Aucun champ tenant, site ou véhicule du message n'est considéré comme fiable.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.fleet.gps_atomic_ingestion import ingest_gps_atomically
from app.fleet.gps_authenticated_device import resolve_authenticated_gps_device
from app.fleet.gps_gateway_contract import GpsDeviceMessage, position_from_trusted_binding


@dataclass(frozen=True)
class TrustedGatewayContext:
    """Contexte validé hors de ce service, jamais construit depuis du JSON."""

    tenant_id: uuid.UUID


def accept_gps_device_message(
    db: Session,
    *,
    context: TrustedGatewayContext,
    message: GpsDeviceMessage,
    supplied_secret: str,
    received_at: datetime,
) -> bool:
    """Authentifier le traceur et tenter l'enregistrement anti-rejeu."""
    if context.tenant_id.int == 0:
        return False
    if received_at.tzinfo is None or received_at.utcoffset() is None:
        return False
    binding = resolve_authenticated_gps_device(
        db,
        trusted_tenant_id=context.tenant_id,
        device_id=message.device_id,
        supplied_secret=supplied_secret,
        at=received_at,
    )
    if binding is None or binding.tenant_id != context.tenant_id:
        return False
    position = position_from_trusted_binding(binding, message)
    if position is None:
        return False
    return ingest_gps_atomically(
        db,
        tenant_id=binding.tenant_id,
        site_id=binding.site_id,
        position=position,
        supplied_secret=supplied_secret,
        received_at=received_at,
        sequence=message.sequence,
    )
