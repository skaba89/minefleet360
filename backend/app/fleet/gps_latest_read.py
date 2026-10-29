"""Lecture interne des dernières positions GPS sans fuite entre sites ou sociétés."""

from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.fleet.gps_models import FleetGpsPosition

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
    ranked = (
        select(
            FleetGpsPosition.gps_position_id.label("position_id"),
            func.row_number()
            .over(
                partition_by=FleetGpsPosition.vehicle_id,
                order_by=(
                    FleetGpsPosition.recorded_at.desc(),
                    FleetGpsPosition.received_at.desc(),
                    FleetGpsPosition.gps_position_id.desc(),
                ),
            )
            .label("rn"),
        )
        .where(
            FleetGpsPosition.tenant_id == auth.tenant_id,
            FleetGpsPosition.recorded_at <= as_of + timedelta(minutes=2),
        )
        .subquery()
    )
    statement = (
        select(FleetGpsPosition)
        .join(ranked, FleetGpsPosition.gps_position_id == ranked.c.position_id)
        .where(ranked.c.rn == 1, FleetGpsPosition.tenant_id == auth.tenant_id)
        .order_by(FleetGpsPosition.vehicle_id)
    )
    rows = auth.db.execute(statement).scalars().all()
    return [
        position
        for position in rows
        if auth.scope.covers_site(position.site_id)
        and (site_id is None or str(position.site_id) == site_id)
    ]
