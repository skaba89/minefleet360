"""Contrat public du module assignment : affectations ouvertes bloquant statut et site (D-11, D-13)."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assignment.models import VehicleAssignment
from app.authz.principal import Principal, evaluate
from app.core.config import get_settings
from app.core.errors import AppError

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


def ensure_no_open_assignments(
    db: Session,
    principal: Principal,
    site_id: uuid.UUID,
    *,
    vehicle_id: uuid.UUID | None = None,
    driver_id: uuid.UUID | None = None,
) -> None:
    """409 `OPEN_ASSIGNMENTS_EXIST` (D-11, D-13).

    La liste des affectations n'est jointe que si l'appelant peut les lire sur ce site (SEC1C-05) :
    TENANT_ADMIN change le statut d'un véhicule sans lire les affectations (D-10) et ne reçoit que le total.
    """
    blockers = open_assignments(db, vehicle_id=vehicle_id, driver_id=driver_id)
    if not blockers:
        return
    details: dict[str, Any] = {"total": len(blockers)}
    scope = evaluate(principal, "assignment.vehicle_assignment.read")
    if scope is not None and scope.covers_site(site_id):
        details["items"] = blockers[: get_settings().blocking_list_max]
    raise AppError("OPEN_ASSIGNMENTS_EXIST", details=details)
