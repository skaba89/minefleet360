"""Contrat public du module assignment : affectations ouvertes bloquant statut et site (D-11, D-13)."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assignment.models import VehicleAssignment

# SUSPENDED occupe toujours le créneau (D-30) : il bloque comme PLANNED et ACTIVE.
OPEN_STATUSES = ("PLANNED", "ACTIVE", "SUSPENDED")


def open_assignments(
    db: Session, *, vehicle_id: uuid.UUID | None = None, driver_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    """Affectations ouvertes du véhicule OU du conducteur, triées par début (liste renvoyée dans le 409)."""
    if (vehicle_id is None) == (driver_id is None):
        raise ValueError("indiquer exactement un véhicule ou un conducteur")
    stmt = select(
        VehicleAssignment.vehicle_assignment_id,
        VehicleAssignment.status,
        VehicleAssignment.valid_from,
        VehicleAssignment.valid_to,
    ).where(VehicleAssignment.status.in_(OPEN_STATUSES))
    if vehicle_id is not None:
        stmt = stmt.where(VehicleAssignment.vehicle_id == vehicle_id)
    else:
        stmt = stmt.where(VehicleAssignment.driver_id == driver_id)
    rows = db.execute(stmt.order_by(VehicleAssignment.valid_from, VehicleAssignment.vehicle_assignment_id))
    return [
        {
            "vehicle_assignment_id": str(r.vehicle_assignment_id),
            "status": r.status,
            "valid_from": r.valid_from.isoformat(),
            "valid_to": r.valid_to.isoformat() if r.valid_to else None,
        }
        for r in rows
    ]
