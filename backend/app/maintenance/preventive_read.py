"""Lecture interne des plans et échéances préventives (lot 3b.4).

Ce module ne constitue pas une API publique : le contrôleur appelant devra
vérifier sa permission et sa portée de site avant toute invocation. La RLS
PostgreSQL reste une seconde barrière indépendante.
"""

import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.maintenance.preventive_models import MaintenanceDue, MaintenancePlan


def plans_query(
    tenant_id: uuid.UUID, vehicle_id: uuid.UUID, *, active_only: bool = False
) -> Select[MaintenancePlan]:
    """Restreint explicitement la requête au tenant et au véhicule demandés."""
    stmt = select(MaintenancePlan).where(
        MaintenancePlan.tenant_id == tenant_id,
        MaintenancePlan.vehicle_id == vehicle_id,
    )
    if active_only:
        stmt = stmt.where(MaintenancePlan.active.is_(True))
    return stmt.order_by(MaintenancePlan.code, MaintenancePlan.version.desc())


def dues_query(tenant_id: uuid.UUID, vehicle_id: uuid.UUID) -> Select[MaintenanceDue]:
    """La lecture d'échéances est toujours bornée au même tenant et véhicule."""
    return (
        select(MaintenanceDue)
        .where(
            MaintenanceDue.tenant_id == tenant_id,
            MaintenanceDue.vehicle_id == vehicle_id,
        )
        .order_by(MaintenanceDue.evaluated_at.desc(), MaintenanceDue.maintenance_due_id)
    )


def list_plans(
    db: Session, tenant_id: uuid.UUID, vehicle_id: uuid.UUID, *, active_only: bool = False
) -> list[MaintenancePlan]:
    return list(db.scalars(plans_query(tenant_id, vehicle_id, active_only=active_only)))


def list_dues(db: Session, tenant_id: uuid.UUID, vehicle_id: uuid.UUID) -> list[MaintenanceDue]:
    return list(db.scalars(dues_query(tenant_id, vehicle_id)))
