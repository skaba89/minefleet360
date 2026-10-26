"""Contrats publics du personnel pour les autres modules."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.workforce.models import Driver


def site_blockers(db: Session, site_id: uuid.UUID, limit: int) -> tuple[int, list[dict[str, str]]]:
    """Conducteurs non inactifs du site courant; aucune identité personnelle exposée (RLS)."""
    rows = db.execute(
        select(Driver.driver_id, func.count().over().label("total"))
        .where(Driver.site_id == site_id, Driver.status != "INACTIVE")
        .order_by(Driver.driver_id)
        .limit(max(1, limit))
    ).all()
    return (int(rows[0].total) if rows else 0), [
        {"entity_type": "driver", "entity_id": str(row.driver_id)} for row in rows[: max(0, limit)]
    ]
