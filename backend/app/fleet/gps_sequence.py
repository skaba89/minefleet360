"""Compteur anti-rejeu atomique pour une association GPS authentifiée.

À appeler dans la MÊME transaction que l'insertion de position ; en cas
d'échec de l'insertion, annuler toute la transaction. Les équipements doivent
produire un numéro de séquence strictement croissant par association.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

_ADVANCE_SQL = text(
    """
    INSERT INTO fleet_gps_device_sequence (
      tenant_id, gps_device_binding_id, last_sequence
    ) VALUES (:tenant_id, :binding_id, :sequence)
    ON CONFLICT (tenant_id, gps_device_binding_id)
    DO UPDATE SET
      last_sequence = EXCLUDED.last_sequence,
      updated_at = now()
    WHERE fleet_gps_device_sequence.last_sequence < EXCLUDED.last_sequence
    RETURNING last_sequence
    """
)


def advance_gps_sequence(db: Session, *, tenant_id: uuid.UUID, binding_id: uuid.UUID, sequence: int) -> bool:
    """Accepter seulement une séquence nouvelle, atomiquement en PostgreSQL."""
    if tenant_id.int == 0 or binding_id.int == 0:
        return False
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        return False
    if not 0 <= sequence <= 9223372036854775807:
        return False
    return (
        db.execute(
            _ADVANCE_SQL,
            {"tenant_id": tenant_id, "binding_id": binding_id, "sequence": sequence},
        ).scalar_one_or_none()
        is not None
    )
