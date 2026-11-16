"""Contrat public du module partenaires (rattachement des engins sous-traités par la flotte)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.partners.models import Subcontractor


def subcontractor_status(db: Session, subcontractor_id: uuid.UUID) -> str | None:
    """Statut d'un sous-traitant du tenant courant (RLS), ou None s'il n'existe pas pour ce tenant."""
    return db.execute(
        select(Subcontractor.status).where(Subcontractor.subcontractor_id == subcontractor_id)
    ).scalar_one_or_none()
