"""Lecture PostgreSQL des plans actifs dans le périmètre autorisé.

Ce lot ne fabrique ni dernier entretien ni kilométrage cumulé : ces
références devront être vérifiées avant de calculer les échéances.
"""

import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.fleet.models import Vehicle
from app.maintenance.preventive_models import MaintenancePlan


def active_plans_query(
    tenant_id: uuid.UUID, site_ids: frozenset[uuid.UUID] | None = None
) -> Select[MaintenancePlan]:
    """Requête tenant explicite ; None = accès tenant, ensemble vide = aucun site."""
    query = (
        select(MaintenancePlan)
        .join(
            Vehicle,
            (Vehicle.vehicle_id == MaintenancePlan.vehicle_id)
            & (Vehicle.tenant_id == MaintenancePlan.tenant_id),
        )
        .where(
            MaintenancePlan.tenant_id == tenant_id,
            Vehicle.tenant_id == tenant_id,
            MaintenancePlan.active.is_(True),
            Vehicle.status != "RETIRED",
        )
        .order_by(MaintenancePlan.vehicle_id, MaintenancePlan.code, MaintenancePlan.version)
    )
    if site_ids is not None:
        query = query.where(Vehicle.site_id.in_(site_ids))
    return query


def load_active_plans(
    db: Session,
    tenant_id: uuid.UUID,
    site_ids: frozenset[uuid.UUID] | None = None,
) -> list[MaintenancePlan]:
    """À appeler uniquement après établissement du contexte RLS de la session."""
    return list(db.scalars(active_plans_query(tenant_id, site_ids)))
