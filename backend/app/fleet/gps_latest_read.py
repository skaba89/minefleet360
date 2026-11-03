"""Lecture interne des dernières positions GPS sans fuite entre sites ou sociétés."""

from datetime import datetime, timedelta

from sqlalchemy import select, true

from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.fleet.gps_models import FleetGpsPosition
from app.fleet.models import Vehicle

READ_PERMISSION = "fleet.vehicle.read"


def latest_visible_positions(
    auth: Authorized, *, as_of: datetime, site_id: str | None = None
) -> list[FleetGpsPosition]:
    """Une position par véhicule, accessible uniquement dans le périmètre du lecteur.

    Le statut hors ligne appartient à la présentation : une position ancienne
    ne doit jamais être présentée comme une localisation en direct.
    """
    if auth.scope.permission != READ_PERMISSION:
        raise AppError("PERMISSION_DENIED")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise AppError("VALIDATION_ERROR")
    # Dernière position de CHAQUE véhicule par une lecture indexée (ix_fgp_latest : tenant, véhicule,
    # recorded_at DESC) : coût proportionnel au nombre de véhicules, et non à tout l'historique conservé
    # (l'ancienne fonction de fenêtre lisait et triait toutes les positions de la société).
    # Même départage qu'avant (recorded_at, received_at, identifiant) ; la position retenue reste exclue si
    # elle a été relevée sur un autre site que le site actuel du véhicule.
    latest = (
        select(FleetGpsPosition.gps_position_id)
        .where(
            FleetGpsPosition.tenant_id == Vehicle.tenant_id,
            FleetGpsPosition.vehicle_id == Vehicle.vehicle_id,
            FleetGpsPosition.recorded_at <= as_of + timedelta(minutes=2),
        )
        .order_by(
            FleetGpsPosition.recorded_at.desc(),
            FleetGpsPosition.received_at.desc(),
            FleetGpsPosition.gps_position_id.desc(),
        )
        .limit(1)
        .correlate(Vehicle)
        .lateral("latest")
    )
    statement = (
        select(FleetGpsPosition)
        .select_from(Vehicle)
        .join(latest, true())
        .join(FleetGpsPosition, FleetGpsPosition.gps_position_id == latest.c.gps_position_id)
        .where(
            Vehicle.tenant_id == auth.tenant_id,
            FleetGpsPosition.tenant_id == auth.tenant_id,
            FleetGpsPosition.site_id == Vehicle.site_id,
        )
        .order_by(FleetGpsPosition.vehicle_id)
    )
    rows = auth.db.execute(statement).scalars().all()
    return [
        position
        for position in rows
        if auth.scope.covers_site(position.site_id) and (site_id is None or str(position.site_id) == site_id)
    ]
