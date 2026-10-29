"""Réception interne atomique : séquence et position dans la même sauvegarde SQL.

L'identité du tenant et du site vient exclusivement d'une passerelle fiable.
Aucun endpoint public n'est exposé par ce module.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.fleet.gps_binding_lookup import resolve_gps_binding
from app.fleet.gps_contract import GpsPosition
from app.fleet.gps_ingestion_preflight import preflight_gps_ingestion
from app.fleet.gps_position_write import persist_validated_gps_position
from app.fleet.gps_sequence import advance_gps_sequence


class _RejectGpsPosition(Exception):
    """Annuler le savepoint quand le point n'est pas inséré."""


def ingest_gps_atomically(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    position: GpsPosition,
    supplied_secret: str,
    received_at: datetime,
    sequence: int,
) -> bool:
    """Refuser un rejeu ou doublon sans avancer le compteur en base.

    L'appelant reste responsable du commit/rollback de la transaction externe.
    """
    if not preflight_gps_ingestion(
        db,
        tenant_id=tenant_id,
        site_id=site_id,
        position=position,
        supplied_secret=supplied_secret,
        received_at=received_at,
    ):
        return False
    binding = resolve_gps_binding(
        db,
        tenant_id=tenant_id,
        vehicle_id=position.vehicle_id,
        site_id=site_id,
        device_id=position.device_id,
        recorded_at=received_at,
    )
    if binding is None or binding.revoked_at is not None:
        return False
    try:
        with db.begin_nested():
            if not advance_gps_sequence(
                db,
                tenant_id=tenant_id,
                binding_id=binding.gps_device_binding_id,
                sequence=sequence,
            ):
                raise _RejectGpsPosition
            if not persist_validated_gps_position(
                db,
                tenant_id=tenant_id,
                site_id=site_id,
                position=position,
                supplied_secret=supplied_secret,
                received_at=received_at,
            ):
                raise _RejectGpsPosition
    except _RejectGpsPosition:
        return False
    return True
