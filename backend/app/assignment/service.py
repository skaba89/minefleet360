"""Services d'affectation (US-1.22 à US-1.25, D-27, D-29, D-30).

Portée : véhicule, conducteur et affectation partagent le même site (D-13) ; la portée de l'utilisateur
s'applique au site de l'affectation. Le non-chevauchement est garanti par la base (EXCLUDE) ; les
contrôles applicatifs donnent l'ordre et les codes d'erreur, la base reste le dernier rempart (A4).
Verrous : véhicule puis conducteur, en FOR NO KEY UPDATE (D-32), contre un changement de statut concurrent.
"""

import uuid
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, func, literal, select
from sqlalchemy.orm import Session

from app.assignment.eligibility import Evaluation, Finding, compliance, evaluate
from app.assignment.models import VehicleAssignment
from app.assignment.schemas import (
    AssignmentCancel,
    AssignmentComplete,
    AssignmentCreate,
    AssignmentOut,
    AssignmentSuspend,
    ComplianceOut,
    Issue,
)
from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.authz.principal import evaluate as evaluate_permission
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.http import PageParams, check_version
from app.core.logging import security_logger
from app.fleet.contracts import VehicleFacts, vehicle_facts
from app.organization.contracts import site_timezone
from app.workforce.contracts import DriverFacts, driver_facts

_AUDITED = ("site_id", "vehicle_id", "driver_id", "valid_from", "valid_to", "shift_code", "status")


def _snapshot(a: VehicleAssignment) -> dict[str, Any]:
    """Identifiants, dates et statut seulement : jamais de nom ni de matricule (D-10, SEC1B-02)."""
    values = {name: getattr(a, name) for name in _AUDITED}
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in values.items()}


def _issues(findings: list[Finding]) -> list[Issue]:
    return [Issue(code=f.code, date=f.date) for f in findings]


class _Facts:
    """Faits chargés en lot pour sérialiser ou évaluer plusieurs affectations sans requêtes N+1."""

    def __init__(
        self, db: Session, vehicles: dict[uuid.UUID, VehicleFacts], drivers: dict[uuid.UUID, DriverFacts]
    ):
        self.db = db
        self.vehicles = vehicles
        self.drivers = drivers
        self._zones: dict[uuid.UUID, ZoneInfo] = {}

    @classmethod
    def load(cls, db: Session, assignments: list[VehicleAssignment]) -> "_Facts":
        return cls(
            db,
            vehicle_facts(db, {a.vehicle_id for a in assignments}),
            driver_facts(db, {a.driver_id for a in assignments}),
        )

    def tz(self, site_id: uuid.UUID) -> ZoneInfo:
        if site_id not in self._zones:
            self._zones[site_id] = site_timezone(self.db, site_id)
        return self._zones[site_id]


# Motifs dont le code ou la date révèlent l'état d'un permis ou d'une habilitation (SEC1C-06).
_DOCUMENT_PERMISSION = {
    "LICENSE_EXPIRED": "workforce.driver_license.read",
    "LICENSE_EXPIRING": "workforce.driver_license.read",
    "QUALIFICATION_EXPIRED": "workforce.driver_qualification.read",
    "QUALIFICATION_EXPIRING": "workforce.driver_qualification.read",
}


def _visible(auth: Authorized, site_id: uuid.UUID, findings: list[Finding]) -> list[Finding]:
    """Ne garde que les motifs lisibles par l'appelant sur ce site (permis, habilitations : D-15).

    Le statut de conformité reste visible de tous les lecteurs : c'est l'alerte opérationnelle.
    """
    allowed: dict[str, bool] = {}
    for permission in set(_DOCUMENT_PERMISSION.values()):
        scope = evaluate_permission(auth.principal, permission)
        allowed[permission] = scope is not None and scope.covers_site(site_id)
    # NEXT_EXPIRY : échéance la plus proche du permis ou de l'habilitation → exige les deux lectures.
    allowed["NEXT_EXPIRY"] = all(allowed.values())
    return [
        f
        for f in findings
        if allowed.get(
            "NEXT_EXPIRY" if f.code == "NEXT_EXPIRY" else _DOCUMENT_PERMISSION.get(f.code, ""), True
        )
    ]


def _compliance(auth: Authorized, facts: _Facts, a: VehicleAssignment, now: datetime) -> ComplianceOut:
    reasons, warnings = compliance(
        facts.vehicles[a.vehicle_id],
        facts.drivers[a.driver_id],
        now=now,
        tz=facts.tz(a.site_id),
        warning_days=get_settings().expiry_warning_days,
    )
    return ComplianceOut(
        status="NON_COMPLIANT" if reasons else "COMPLIANT",
        reasons=_issues(_visible(auth, a.site_id, reasons)),
        warnings=_issues(_visible(auth, a.site_id, warnings)),
    )


def _out(
    auth: Authorized,
    facts: _Facts,
    a: VehicleAssignment,
    now: datetime,
    warnings: list[Finding] | None = None,
) -> AssignmentOut:
    vehicle, driver = facts.vehicles[a.vehicle_id], facts.drivers[a.driver_id]
    data: dict[str, Any] = {
        "vehicle_assignment_id": a.vehicle_assignment_id,
        "site_id": a.site_id,
        "vehicle_id": a.vehicle_id,
        "vehicle_fleet_number": vehicle.fleet_number,
        "driver_id": a.driver_id,
        "driver_display_name": driver.display_name,
        "driver_employee_number": driver.employee_number,
        "valid_from": a.valid_from,
        "valid_to": a.valid_to,
        "shift_code": a.shift_code,
        "status": a.status,
        "status_reason": a.status_reason,
        "activation_overdue": a.status == "PLANNED" and a.valid_from <= now,
        "activated_at": a.activated_at,
        "end_overdue": a.status in ("ACTIVE", "SUSPENDED") and a.valid_to is not None and a.valid_to <= now,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
        "row_version": a.row_version,
    }
    if a.status == "ACTIVE":
        data["compliance"] = _compliance(auth, facts, a, now)
    visible_warnings = _visible(auth, a.site_id, warnings or [])
    if visible_warnings:
        data["warnings"] = _issues(visible_warnings)
    return AssignmentOut(**data)


def assignments_out(auth: Authorized, assignments: list[VehicleAssignment]) -> list[AssignmentOut]:
    facts = _Facts.load(auth.db, assignments)
    now = auth.clock.now()
    return [_out(auth, facts, a, now) for a in assignments]


# --- Lecture ------------------------------------------------------------------------------------------


def assignment_in_scope(
    auth: Authorized, assignment_id: uuid.UUID, *, for_update: bool = False
) -> VehicleAssignment:
    stmt = select(VehicleAssignment).where(VehicleAssignment.vehicle_assignment_id == assignment_id)
    if for_update:
        stmt = stmt.with_for_update(key_share=True)
    assignment = auth.db.execute(stmt).scalar_one_or_none()
    if assignment is None or not auth.scope.covers_site(assignment.site_id):
        security_logger.info(
            "item_not_found", extra={"entity_type": "vehicle_assignment", "entity_id": str(assignment_id)}
        )
        raise AppError("NOT_FOUND")
    return assignment


def ensure_vehicle_visible(auth: Authorized, vehicle_id: uuid.UUID) -> None:
    """Historique par véhicule : 404 si le véhicule est hors tenant ou hors portée (US-1.24 A3)."""
    facts = vehicle_facts(auth.db, [vehicle_id]).get(vehicle_id)
    if facts is None or not auth.scope.covers_site(facts.site_id):
        security_logger.info("item_not_found", extra={"entity_type": "vehicle", "entity_id": str(vehicle_id)})
        raise AppError("NOT_FOUND")


def ensure_driver_visible(auth: Authorized, driver_id: uuid.UUID) -> None:
    facts = driver_facts(auth.db, [driver_id]).get(driver_id)
    if facts is None or not auth.scope.covers_site(facts.site_id):
        security_logger.info("item_not_found", extra={"entity_type": "driver", "entity_id": str(driver_id)})
        raise AppError("NOT_FOUND")


def list_assignments(
    auth: Authorized,
    page: PageParams,
    *,
    site_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    driver_id: uuid.UUID | None = None,
    status: str | None = None,
    at: datetime | None = None,
    compliance_filter: str | None = None,
) -> tuple[list[AssignmentOut], int]:
    stmt = select(VehicleAssignment)
    if not auth.scope.tenant_wide:
        stmt = stmt.where(VehicleAssignment.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        stmt = stmt.where(VehicleAssignment.site_id == site_id)
    if vehicle_id is not None:
        stmt = stmt.where(VehicleAssignment.vehicle_id == vehicle_id)
    if driver_id is not None:
        stmt = stmt.where(VehicleAssignment.driver_id == driver_id)
    if status is not None:
        stmt = stmt.where(VehicleAssignment.status == status)
    if at is not None:
        # « Qui conduisait à l'instant T » : borne de début incluse, de fin exclue (US-1.24 A2).
        stmt = stmt.where(
            VehicleAssignment.status != "CANCELLED",
            VehicleAssignment.valid_during.op("@>")(literal(at, DateTime(timezone=True))),
        )
    ordered = stmt.order_by(VehicleAssignment.valid_from.desc(), VehicleAssignment.vehicle_assignment_id)
    if compliance_filter is None:
        total = auth.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = list(auth.db.execute(ordered.offset(page.offset).limit(page.page_size)).scalars())
        return assignments_out(auth, rows), total
    # Conformité calculée à la lecture (D-12) : filtrée en mémoire sur les affectations ACTIVE, plafonnées.
    limit = get_settings().compliance_scan_max
    candidates = list(
        auth.db.execute(ordered.where(VehicleAssignment.status == "ACTIVE").limit(limit + 1)).scalars()
    )
    if len(candidates) > limit:
        raise AppError("VALIDATION_ERROR", details=[{"field": "compliance", "type": "too_many_results"}])
    matching = [
        o
        for o in assignments_out(auth, candidates)
        if o.compliance and o.compliance.status == compliance_filter
    ]
    return matching[page.offset : page.offset + page.page_size], len(matching)


# --- Écritures ----------------------------------------------------------------------------------------


def _ensure_no_overlap(
    db: Session,
    *,
    vehicle_id: uuid.UUID,
    driver_id: uuid.UUID,
    start: datetime,
    end: datetime | None,
    exclude: uuid.UUID | None = None,
) -> None:
    """Contrôle applicatif dans l'ordre véhicule puis conducteur (US-1.22 §0.4) ; la base fait foi (A4)."""
    window = func.tstzrange(
        literal(start, DateTime(timezone=True)), literal(end, DateTime(timezone=True)), "[)"
    )
    for column, value, code in (
        (VehicleAssignment.vehicle_id, vehicle_id, "VEHICLE_ASSIGNMENT_OVERLAP"),
        (VehicleAssignment.driver_id, driver_id, "DRIVER_ASSIGNMENT_OVERLAP"),
    ):
        stmt = select(VehicleAssignment.vehicle_assignment_id).where(
            column == value,
            VehicleAssignment.status != "CANCELLED",
            VehicleAssignment.valid_during.op("&&")(window),
        )
        if exclude is not None:
            stmt = stmt.where(VehicleAssignment.vehicle_assignment_id != exclude)
        if db.execute(stmt.limit(1)).first() is not None:
            raise AppError(code)


def _not_eligible(ev: Evaluation, extra: list[Finding] | None = None) -> AppError:
    reasons = [*(extra or []), *ev.reasons]
    return AppError("ASSIGNMENT_NOT_ELIGIBLE", details={"reasons": [r.as_dict() for r in reasons]})


def _locked_facts(
    auth: Authorized, a_vehicle: uuid.UUID, a_driver: uuid.UUID
) -> tuple[_Facts, VehicleFacts, DriverFacts]:
    """Verrouille véhicule puis conducteur (ordre fixe : pas d'interblocage entre créations)."""
    vehicles = vehicle_facts(auth.db, [a_vehicle], lock=True)
    drivers = driver_facts(auth.db, [a_driver], lock=True)
    facts = _Facts(auth.db, vehicles, drivers)
    return facts, vehicles[a_vehicle], drivers[a_driver]


def create_assignment(auth: Authorized, body: AssignmentCreate) -> AssignmentOut:
    """US-1.22 : ordre format → références → éligibilité (tous motifs, D-29) → chevauchements."""
    db, settings = auth.db, get_settings()
    now = auth.clock.now()
    if body.valid_to is not None and body.valid_to <= body.valid_from:
        raise AppError("END_BEFORE_START")
    vehicles = vehicle_facts(db, [body.vehicle_id], lock=True)
    vehicle = vehicles.get(body.vehicle_id)
    if vehicle is None or not auth.scope.covers_site(vehicle.site_id):
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "vehicle_id"}])
    drivers = driver_facts(db, [body.driver_id], lock=True)
    driver = drivers.get(body.driver_id)
    if driver is None or not auth.scope.covers_site(driver.site_id):
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "driver_id"}])
    facts = _Facts(db, vehicles, drivers)

    pre: list[Finding] = []
    if vehicle.site_id != driver.site_id:
        pre.append(Finding("ASSIGNMENT_SITE_MISMATCH"))
    if body.valid_from < now - settings.assignment_backdate_tolerance:
        pre.append(Finding("ASSIGNMENT_BACKDATED"))
    if body.valid_from > now + settings.assignment_max_horizon:
        # Pas de réservation de créneau lointaine (SEC1C-03) : elle bloquerait statuts et sites (D-11).
        pre.append(Finding("ASSIGNMENT_TOO_FAR_AHEAD"))
    ev = evaluate(
        vehicle,
        driver,
        start=max(body.valid_from, now),
        end=body.valid_to,
        tz=facts.tz(vehicle.site_id),
        warning_days=settings.expiry_warning_days,
    )
    if pre or not ev.eligible:
        raise _not_eligible(ev, pre)
    _ensure_no_overlap(
        db,
        vehicle_id=vehicle.vehicle_id,
        driver_id=driver.driver_id,
        start=body.valid_from,
        end=body.valid_to,
    )

    started = body.valid_from <= now + settings.clock_skew_tolerance
    assignment = VehicleAssignment(
        tenant_id=auth.tenant_id,
        site_id=vehicle.site_id,
        vehicle_id=vehicle.vehicle_id,
        driver_id=driver.driver_id,
        valid_from=body.valid_from.astimezone(UTC),  # stockage et réponse en UTC (A14)
        valid_to=body.valid_to.astimezone(UTC) if body.valid_to else None,
        shift_code=body.shift_code,
        status="ACTIVE" if started else "PLANNED",
        activated_at=now if started else None,
        eligibility_snapshot={
            "evaluated_at": now.isoformat(),
            "license_ids": ev.license_ids,
            "qualification_ids": ev.qualification_ids,
            "warnings": [w.as_dict() for w in ev.warnings],
        },
        created_by=auth.user_id,
        updated_by=auth.user_id,
    )
    db.add(assignment)
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="vehicle_assignment.create",
        entity_type="vehicle_assignment",
        entity_id=assignment.vehicle_assignment_id,
        site_id=assignment.site_id,
        actor_user_id=auth.user_id,
        after=_snapshot(assignment),
    )
    out = _out(auth, facts, assignment, now, ev.warnings)  # avant COMMIT : le contexte tenant disparaît après
    db.commit()
    return out


def _transition(
    auth: Authorized,
    assignment: VehicleAssignment,
    facts: _Facts,
    *,
    action: str,
    target: str,
    reason: str | None,
    valid_to: datetime | None = None,
    activated_at: datetime | None = None,
) -> AssignmentOut:
    db = auth.db
    before = _snapshot(assignment)
    assignment.status = target
    assignment.status_reason = reason
    if valid_to is not None:
        assignment.valid_to = valid_to
    if activated_at is not None:
        assignment.activated_at = activated_at
    assignment.updated_by = auth.user_id
    db.flush()
    after = _snapshot(assignment)
    changed = tuple(k for k in _AUDITED if before[k] != after[k])
    record(
        db,
        tenant_id=auth.tenant_id,
        action=action,
        entity_type="vehicle_assignment",
        entity_id=assignment.vehicle_assignment_id,
        site_id=assignment.site_id,
        actor_user_id=auth.user_id,
        reason=reason,
        before={k: before[k] for k in changed},
        after={k: after[k] for k in changed},
        changed_fields=changed,
    )
    out = _out(auth, facts, assignment, auth.clock.now())
    db.commit()
    return out


def _load_for_update(
    auth: Authorized, assignment_id: uuid.UUID, expected_version: int, allowed: tuple[str, ...]
) -> VehicleAssignment:
    assignment = assignment_in_scope(auth, assignment_id, for_update=True)
    check_version(expected_version, assignment.row_version)
    if assignment.status not in allowed:
        raise AppError(
            "ASSIGNMENT_STATE_INVALID", details={"status": assignment.status, "allowed_from": list(allowed)}
        )
    return assignment


def _recheck(
    auth: Authorized, assignment: VehicleAssignment, facts: _Facts, vehicle: VehicleFacts, driver: DriverFacts
) -> None:
    """Revérification à la prise de poste et à la reprise (RM-031) : de maintenant à la fin prévue."""
    ev = evaluate(
        vehicle,
        driver,
        start=auth.clock.now(),
        end=assignment.valid_to,
        tz=facts.tz(assignment.site_id),
        warning_days=get_settings().expiry_warning_days,
    )
    if not ev.eligible:
        raise _not_eligible(ev)


def activate_assignment(auth: Authorized, assignment_id: uuid.UUID, expected_version: int) -> AssignmentOut:
    """D-27 : prise de poste explicite PLANNED → ACTIVE, éligibilité revérifiée à la date courante."""
    assignment = _load_for_update(auth, assignment_id, expected_version, ("PLANNED",))
    now = auth.clock.now()
    if assignment.valid_from > now + get_settings().clock_skew_tolerance:
        raise AppError("ASSIGNMENT_STATE_INVALID", details={"status": "PLANNED", "reason": "NOT_YET_STARTED"})
    if assignment.valid_to is not None and assignment.valid_to <= now:
        raise AppError("ASSIGNMENT_STATE_INVALID", details={"status": "PLANNED", "reason": "ALREADY_ENDED"})
    facts, vehicle, driver = _locked_facts(auth, assignment.vehicle_id, assignment.driver_id)
    _recheck(auth, assignment, facts, vehicle, driver)
    # Instant réel de prise de poste (SEC1C-R-03) : une activation tardive reste visible et exploitable.
    return _transition(
        auth,
        assignment,
        facts,
        action="vehicle_assignment.activate",
        target="ACTIVE",
        reason=None,
        activated_at=now,
    )


def suspend_assignment(
    auth: Authorized, assignment_id: uuid.UUID, body: AssignmentSuspend, expected_version: int
) -> AssignmentOut:
    """D-30 : suspension manuelle motivée ; le créneau reste occupé."""
    assignment = _load_for_update(auth, assignment_id, expected_version, ("ACTIVE",))
    facts = _Facts.load(auth.db, [assignment])
    return _transition(
        auth,
        assignment,
        facts,
        action="vehicle_assignment.suspend",
        target="SUSPENDED",
        reason=body.reason_code,
    )


def resume_assignment(auth: Authorized, assignment_id: uuid.UUID, expected_version: int) -> AssignmentOut:
    """D-30 : reprise SUSPENDED → ACTIVE, avec la même revérification que la prise de poste."""
    assignment = _load_for_update(auth, assignment_id, expected_version, ("SUSPENDED",))
    if assignment.valid_to is not None and assignment.valid_to <= auth.clock.now():
        raise AppError("ASSIGNMENT_STATE_INVALID", details={"status": "SUSPENDED", "reason": "ALREADY_ENDED"})
    facts, vehicle, driver = _locked_facts(auth, assignment.vehicle_id, assignment.driver_id)
    _recheck(auth, assignment, facts, vehicle, driver)
    return _transition(
        auth, assignment, facts, action="vehicle_assignment.resume", target="ACTIVE", reason=None
    )


def complete_assignment(
    auth: Authorized, assignment_id: uuid.UUID, body: AssignmentComplete, expected_version: int
) -> AssignmentOut:
    """US-1.23 A1 : clôture d'une affectation en cours, fin réelle tronquée (jamais prolongée au lot 1).

    Fin rétroactive bornée comme le début (SEC1C-R-01) : au plus la tolérance d'antidatage, sauf la fin
    prévue elle-même (affectation arrivée à échéance, clôturée après coup). Sans `ended_at` : maintenant,
    ou la fin prévue si elle est déjà passée.
    """
    assignment = _load_for_update(auth, assignment_id, expected_version, ("ACTIVE", "SUSPENDED"))
    now = auth.clock.now()
    settings = get_settings()
    planned_end = assignment.valid_to
    default_end = min(now, planned_end) if planned_end is not None else now
    ended_at = (body.ended_at or default_end).astimezone(UTC)
    if ended_at <= assignment.valid_from:
        raise AppError("END_BEFORE_START")
    if ended_at > now + settings.assignment_end_future_tolerance:
        raise AppError("END_IN_FUTURE")
    if ended_at < now - settings.assignment_backdate_tolerance and ended_at != planned_end:
        raise AppError("END_BACKDATED")
    if assignment.valid_to is not None and ended_at > assignment.valid_to:
        raise AppError("VALIDATION_ERROR", details=[{"field": "ended_at", "type": "after_planned_end"}])
    facts = _Facts.load(auth.db, [assignment])
    return _transition(
        auth,
        assignment,
        facts,
        action="vehicle_assignment.complete",
        target="COMPLETED",
        reason=body.reason_code,
        valid_to=ended_at,
    )


def cancel_assignment(
    auth: Authorized, assignment_id: uuid.UUID, body: AssignmentCancel, expected_version: int
) -> AssignmentOut:
    """US-1.23 A5 : annulation motivée d'une affectation PLANNED ; ressources libérées immédiatement."""
    assignment = _load_for_update(auth, assignment_id, expected_version, ("PLANNED",))
    facts = _Facts.load(auth.db, [assignment])
    return _transition(
        auth,
        assignment,
        facts,
        action="vehicle_assignment.cancel",
        target="CANCELLED",
        reason=body.reason_code,
    )
