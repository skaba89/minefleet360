"""Contrat public du module assignment : affectations ouvertes bloquant statut et site (D-11, D-13)."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assignment.eligibility import compliance
from app.assignment.models import VehicleAssignment
from app.audit.contracts import record
from app.authz.principal import Principal, evaluate
from app.core.config import get_settings
from app.core.errors import AppError
from app.fleet.contracts import vehicle_facts
from app.organization.contracts import site_timezone
from app.workforce.contracts import driver_facts

# SUSPENDED occupe toujours le créneau (D-30) : il bloque comme PLANNED et ACTIVE.
OPEN_STATUSES = ("PLANNED", "ACTIVE", "SUSPENDED")

# Statuts de sécurité soumis à la politique D-41 ; réforme, sortie définitive et changement de site
# restent toujours bloqués par une affectation ouverte (D-11, D-13).
SAFETY_VEHICLE_STATUSES = frozenset({"IN_MAINTENANCE", "IMMOBILIZED", "OUT_OF_SERVICE"})
SAFETY_DRIVER_STATUSES = frozenset({"UNAVAILABLE", "SUSPENDED"})


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


def apply_safety_policy(
    db: Session,
    principal: Principal,
    site_id: uuid.UUID,
    *,
    now: datetime,
    vehicle_id: uuid.UUID | None = None,
    driver_id: uuid.UUID | None = None,
) -> None:
    """Statut de sécurité d'un véhicule ou d'un conducteur affecté, selon MF_ASSIGNMENT_SAFETY_POLICY (D-41).

    - block : 409 comme D-11 ;
    - flag  : rien à faire ici, la conformité dérivée signale l'affectation (VEHICLE_NOT_AVAILABLE,
      DRIVER_NOT_ACTIVE) et la prise de poste d'une affectation planifiée sera refusée ;
    - close : affectations planifiées annulées, en cours clôturées maintenant (ou à leur fin prévue si
      elle est déjà passée), chacune auditée au nom de l'auteur du changement de statut.
    """
    policy = get_settings().assignment_safety_policy
    if policy == "block":
        ensure_no_open_assignments(db, principal, site_id, vehicle_id=vehicle_id, driver_id=driver_id)
        return
    if policy == "flag":
        return
    stmt = select(VehicleAssignment).where(VehicleAssignment.status.in_(OPEN_STATUSES))
    if vehicle_id is not None:
        stmt = stmt.where(VehicleAssignment.vehicle_id == vehicle_id)
        cause = "VEHICLE_UNAVAILABLE"
    else:
        stmt = stmt.where(VehicleAssignment.driver_id == driver_id)
        cause = "DRIVER_UNAVAILABLE"
    for assignment in db.execute(stmt.with_for_update(key_share=True)).scalars():
        before = assignment.status
        end = min(now, assignment.valid_to) if assignment.valid_to is not None else now
        if before == "PLANNED" or end <= assignment.valid_from:
            assignment.status, assignment.status_reason = "CANCELLED", cause
        else:
            assignment.status, assignment.status_reason, assignment.valid_to = "COMPLETED", "SAFETY_STOP", end
        assignment.updated_by = principal.user_id
        record(
            db,
            tenant_id=principal.tenant_id,
            action="vehicle_assignment.auto_close",
            entity_type="vehicle_assignment",
            entity_id=assignment.vehicle_assignment_id,
            site_id=assignment.site_id,
            actor_user_id=principal.user_id,
            reason=cause,
            before={"status": before},
            after={"status": assignment.status},
            changed_fields=("status", "status_reason"),
        )
    db.flush()


# --- Contrat pour le dispatch (lot 2) : affectation porteuse d'une mission ------------------------------


@dataclass(frozen=True)
class AssignmentFacts:
    vehicle_assignment_id: uuid.UUID
    site_id: uuid.UUID
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID
    status: str
    valid_from: datetime
    valid_to: datetime | None


def assignment_facts(db: Session, assignment_id: uuid.UUID) -> AssignmentFacts | None:
    """Affectation du tenant courant (RLS) ; la portée site est contrôlée par l'appelant."""
    row = db.get(VehicleAssignment, assignment_id)
    if row is None:
        return None
    return AssignmentFacts(
        row.vehicle_assignment_id,
        row.site_id,
        row.vehicle_id,
        row.driver_id,
        row.status,
        row.valid_from,
        row.valid_to,
    )


def running_blockers(db: Session, facts: AssignmentFacts, now: datetime) -> list[str]:
    """Motifs empêchant de rouler maintenant (RM-080) : affectation non active ou non conforme."""
    reasons: list[str] = []
    if facts.status != "ACTIVE":
        reasons.append("ASSIGNMENT_NOT_ACTIVE")
    if facts.valid_to is not None and facts.valid_to <= now:
        reasons.append("ASSIGNMENT_ENDED")
    vehicle = vehicle_facts(db, [facts.vehicle_id]).get(facts.vehicle_id)
    driver = driver_facts(db, [facts.driver_id]).get(facts.driver_id)
    if vehicle is None or driver is None:
        return [*reasons, "REFERENCE_NOT_FOUND"]
    found, _ = compliance(
        vehicle,
        driver,
        now=now,
        tz=site_timezone(db, facts.site_id),
        warning_days=get_settings().expiry_warning_days,
    )
    return reasons + [f.code for f in found]
