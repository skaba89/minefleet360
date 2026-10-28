"""Service de lecture préventive : autorisation par entreprise et site avant accès.

Aucune route publique et aucune mutation. La RLS en base demeure obligatoire.
"""

import uuid

from sqlalchemy import select

from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.fleet.models import Vehicle
from app.maintenance.preventive_models import MaintenanceDue, MaintenancePlan
from app.maintenance.preventive_read import list_dues, list_plans


def _ensure_vehicle_in_scope(auth: Authorized, vehicle_id: uuid.UUID) -> None:
    """Retour 404 uniforme pour tout véhicule inexistant ou hors portée."""
    vehicle = auth.db.execute(
        select(Vehicle).where(
            Vehicle.tenant_id == auth.tenant_id,
            Vehicle.vehicle_id == vehicle_id,
        )
    ).scalar_one_or_none()
    if vehicle is None or not auth.scope.covers_site(vehicle.site_id):
        raise AppError("NOT_FOUND")


def plans_for_vehicle(
    auth: Authorized, vehicle_id: uuid.UUID, *, active_only: bool = False
) -> list[MaintenancePlan]:
    """À invoquer via une permission Require(...), jamais depuis une route non protégée."""
    _ensure_vehicle_in_scope(auth, vehicle_id)
    return list_plans(auth.db, auth.tenant_id, vehicle_id, active_only=active_only)


def dues_for_vehicle(auth: Authorized, vehicle_id: uuid.UUID) -> list[MaintenanceDue]:
    """Vérifie la portée site avant lecture des échéances."""
    _ensure_vehicle_in_scope(auth, vehicle_id)
    return list_dues(auth.db, auth.tenant_id, vehicle_id)
