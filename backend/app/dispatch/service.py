"""Services dispatch (lot 2a, docs/PLAN_LOT2.md) : lieux, matières, missions, avancement, rotations.

- Une mission porte une affectation du même site (véhicule et conducteur éligibles) ; le départ exige
  une affectation active et conforme (RM-080).
- Chaque transition écrit un événement immuable et met à jour le statut dans la même transaction,
  avec audit. Les rotations sont DÉRIVÉES des événements (chargement → déchargement), sans tonnage.
- Renvoi d'un même `client_event_id` : aucun doublon, réponse identique (RM-084).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.assignment.contracts import AssignmentFacts, assignment_facts, running_blockers
from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.authz.principal import evaluate
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.http import PageParams, check_version
from app.core.logging import security_logger
from app.dispatch.models import Material, Mission, MissionEvent, Rotation, SiteLocation
from app.dispatch.schemas import (
    EventOut,
    LocationCreate,
    LocationUpdate,
    MaterialCreate,
    MaterialUpdate,
    MissionCreate,
    MissionEventCreate,
    MissionOut,
    RotationOut,
)
from app.fleet.contracts import vehicle_facts
from app.organization.contracts import active_site_in_scope
from app.workforce.contracts import driver_facts

RUNNING = frozenset({"EN_ROUTE_EMPTY", "LOADING", "EN_ROUTE_LOADED", "UNLOADING"})
SUSPENDABLE = frozenset({"ASSIGNED", *RUNNING})
TERMINAL = frozenset({"COMPLETED", "CANCELLED"})
# event → (états de départ admis, état d'arrivée) ; SUSPENDED/RESUMED/REASSIGNED/COMPLETED traités à part.
PROGRESS: dict[str, tuple[frozenset[str], str]] = {
    "DEPARTED": (frozenset({"ASSIGNED"}), "EN_ROUTE_EMPTY"),
    "ARRIVED_LOADING": (frozenset({"EN_ROUTE_EMPTY"}), "LOADING"),
    "LOADED": (frozenset({"LOADING"}), "EN_ROUTE_LOADED"),
    "ARRIVED_UNLOADING": (frozenset({"EN_ROUTE_LOADED"}), "UNLOADING"),
    "UNLOADED": (frozenset({"UNLOADING"}), "EN_ROUTE_EMPTY"),
}


# --- Référentiels ---------------------------------------------------------------------------------------


def _location_in_scope(auth: Authorized, location_id: uuid.UUID, *, for_update: bool = False) -> SiteLocation:
    stmt = select(SiteLocation).where(SiteLocation.site_location_id == location_id)
    if for_update:
        stmt = stmt.with_for_update(key_share=True)
    location = auth.db.execute(stmt).scalar_one_or_none()
    if location is None or not auth.scope.covers_site(location.site_id):
        security_logger.info(
            "item_not_found", extra={"entity_type": "site_location", "entity_id": str(location_id)}
        )
        raise AppError("NOT_FOUND")
    return location


def list_locations(
    auth: Authorized, *, site_id: uuid.UUID | None, include_inactive: bool
) -> list[SiteLocation]:
    stmt = select(SiteLocation)
    if not auth.scope.tenant_wide:
        stmt = stmt.where(SiteLocation.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        stmt = stmt.where(SiteLocation.site_id == site_id)
    if not include_inactive:
        stmt = stmt.where(SiteLocation.status == "ACTIVE")
    return list(auth.db.execute(stmt.order_by(SiteLocation.site_id, SiteLocation.code)).scalars())


def create_location(auth: Authorized, body: LocationCreate) -> SiteLocation:
    db = auth.db
    if active_site_in_scope(db, auth.scope, body.site_id) is None:
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "site_id"}])
    location = SiteLocation(
        tenant_id=auth.tenant_id, **body.model_dump(), created_by=auth.user_id, updated_by=auth.user_id
    )
    db.add(location)
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="site_location.create",
        entity_type="site_location",
        entity_id=location.site_location_id,
        site_id=location.site_id,
        actor_user_id=auth.user_id,
        after={"code": location.code, "kind": location.kind},
    )
    db.commit()
    return location


def update_location(
    auth: Authorized, location_id: uuid.UUID, body: LocationUpdate, version: int
) -> SiteLocation:
    db = auth.db
    location = _location_in_scope(auth, location_id, for_update=True)
    check_version(version, location.row_version)
    fields = tuple(sorted(f for f in body.model_fields_set if getattr(body, f) is not None))
    before = {f: getattr(location, f) for f in fields}
    for name in fields:
        setattr(location, name, getattr(body, name))
    location.updated_by = auth.user_id
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="site_location.update",
        entity_type="site_location",
        entity_id=location.site_location_id,
        site_id=location.site_id,
        actor_user_id=auth.user_id,
        before=before,
        after={f: getattr(location, f) for f in fields},
        changed_fields=fields,
    )
    db.commit()
    return location


def list_materials(auth: Authorized, *, include_inactive: bool) -> list[Material]:
    stmt = select(Material)
    if not include_inactive:
        stmt = stmt.where(Material.status == "ACTIVE")
    return list(auth.db.execute(stmt.order_by(Material.code)).scalars())


def create_material(auth: Authorized, body: MaterialCreate) -> Material:
    db = auth.db
    material = Material(
        tenant_id=auth.tenant_id, **body.model_dump(), created_by=auth.user_id, updated_by=auth.user_id
    )
    db.add(material)
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="material.create",
        entity_type="material",
        entity_id=material.material_id,
        actor_user_id=auth.user_id,
        after={"code": material.code, "is_waste": material.is_waste},
    )
    db.commit()
    return material


def update_material(auth: Authorized, material_id: uuid.UUID, body: MaterialUpdate, version: int) -> Material:
    db = auth.db
    material = db.execute(
        select(Material).where(Material.material_id == material_id).with_for_update(key_share=True)
    ).scalar_one_or_none()
    if material is None:
        raise AppError("NOT_FOUND")
    check_version(version, material.row_version)
    fields = tuple(sorted(f for f in body.model_fields_set if getattr(body, f) is not None))
    before = {f: getattr(material, f) for f in fields}
    for name in fields:
        setattr(material, name, getattr(body, name))
    material.updated_by = auth.user_id
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="material.update",
        entity_type="material",
        entity_id=material.material_id,
        actor_user_id=auth.user_id,
        before=before,
        after={f: getattr(material, f) for f in fields},
        changed_fields=fields,
    )
    db.commit()
    return material


# --- Sérialisation des missions ----------------------------------------------------------------------


@dataclass
class _Labels:
    fleet: dict[uuid.UUID, str]
    drivers: dict[uuid.UUID, str]
    locations: dict[uuid.UUID, str]
    materials: dict[uuid.UUID, str]
    completed: dict[uuid.UUID, int]


def _labels(db: Session, missions: list[Mission]) -> _Labels:
    ids = [m.mission_id for m in missions]
    vehicles = vehicle_facts(db, {m.vehicle_id for m in missions})
    drivers = driver_facts(db, {m.driver_id for m in missions})
    place_ids = {m.origin_location_id for m in missions} | {m.destination_location_id for m in missions}
    places = db.execute(
        select(SiteLocation.site_location_id, SiteLocation.name).where(
            SiteLocation.site_location_id.in_(place_ids)
        )
    ).all()
    materials = db.execute(
        select(Material.material_id, Material.name).where(
            Material.material_id.in_({m.material_id for m in missions})
        )
    ).all()
    completed = db.execute(
        select(Rotation.mission_id, func.count())
        .where(Rotation.mission_id.in_(ids), Rotation.status == "COMPLETED")
        .group_by(Rotation.mission_id)
    ).all()
    return _Labels(
        {k: v.fleet_number for k, v in vehicles.items()},
        {k: v.display_name for k, v in drivers.items()},
        {r[0]: r[1] for r in places},
        {r[0]: r[1] for r in materials},
        {r[0]: int(r[1]) for r in completed},
    )


def _rotation_out(r: Rotation) -> RotationOut:
    cycle = (
        int((r.unloaded_at - r.loading_started_at).total_seconds())
        if r.unloaded_at is not None and r.status == "COMPLETED"
        else None
    )
    return RotationOut(
        rotation_id=r.rotation_id,
        sequence=r.sequence,
        vehicle_id=r.vehicle_id,
        loading_started_at=r.loading_started_at,
        loaded_at=r.loaded_at,
        unloading_started_at=r.unloading_started_at,
        unloaded_at=r.unloaded_at,
        status=r.status,
        cycle_seconds=cycle,
    )


def _out(
    db: Session, m: Mission, labels: _Labels, now: datetime, *, show_driver: bool, detail: bool = False
) -> MissionOut:
    data: dict[str, Any] = {
        "mission_id": m.mission_id,
        "site_id": m.site_id,
        "vehicle_assignment_id": m.vehicle_assignment_id,
        "vehicle_id": m.vehicle_id,
        "vehicle_fleet_number": labels.fleet.get(m.vehicle_id, "?"),
        "driver_id": m.driver_id if show_driver else None,
        "driver_display_name": labels.drivers.get(m.driver_id, "?") if show_driver else None,
        "origin_location_id": m.origin_location_id,
        "origin_name": labels.locations.get(m.origin_location_id, "?"),
        "destination_location_id": m.destination_location_id,
        "destination_name": labels.locations.get(m.destination_location_id, "?"),
        "material_id": m.material_id,
        "material_name": labels.materials.get(m.material_id, "?"),
        "planned_start": m.planned_start,
        "due_at": m.due_at,
        "planned_rotations": m.planned_rotations,
        "status": m.status,
        "status_before_suspension": m.status_before_suspension,
        "status_reason": m.status_reason,
        "notes": m.notes,
        "rotations_completed": labels.completed.get(m.mission_id, 0),
        "overdue": m.due_at is not None and m.due_at <= now and m.status not in TERMINAL,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
        "row_version": m.row_version,
    }
    if detail:
        events = db.execute(
            select(MissionEvent)
            .where(MissionEvent.mission_id == m.mission_id)
            .order_by(MissionEvent.occurred_at, MissionEvent.recorded_at, MissionEvent.mission_event_id)
        ).scalars()
        data["events"] = [
            EventOut(
                mission_event_id=e.mission_event_id,
                event_type=e.event_type,
                vehicle_assignment_id=e.vehicle_assignment_id,
                from_status=e.from_status,
                to_status=e.to_status,
                occurred_at=e.occurred_at,
                recorded_at=e.recorded_at,
                source=e.source,
                reason=e.reason,
            )
            for e in events
        ]
        rotations = db.execute(
            select(Rotation).where(Rotation.mission_id == m.mission_id).order_by(Rotation.sequence)
        ).scalars()
        data["rotations"] = [_rotation_out(r) for r in rotations]
    return MissionOut(**data)


def missions_out(auth: Authorized, missions: list[Mission], *, detail: bool = False) -> list[MissionOut]:
    labels = _labels(auth.db, missions)
    now = auth.clock.now()
    # Le nom du conducteur suit les droits de lecture des affectations, pas ceux des missions (L2A-R-02) :
    # FINANCE n'y a pas accès, le chef d'atelier seulement sur son site.
    drivers = evaluate(auth.principal, "assignment.vehicle_assignment.read")
    return [
        _out(
            auth.db,
            m,
            labels,
            now,
            show_driver=drivers is not None and drivers.covers_site(m.site_id),
            detail=detail,
        )
        for m in missions
    ]


# --- Lecture -------------------------------------------------------------------------------------------


def mission_in_scope(auth: Authorized, mission_id: uuid.UUID, *, for_update: bool = False) -> Mission:
    stmt = select(Mission).where(Mission.mission_id == mission_id)
    if for_update:
        stmt = stmt.with_for_update(key_share=True)
    mission = auth.db.execute(stmt).scalar_one_or_none()
    if mission is None or not auth.scope.covers_site(mission.site_id):
        security_logger.info("item_not_found", extra={"entity_type": "mission", "entity_id": str(mission_id)})
        raise AppError("NOT_FOUND")
    return mission


def list_missions(
    auth: Authorized,
    page: PageParams,
    *,
    site_id: uuid.UUID | None,
    status: str | None,
    vehicle_id: uuid.UUID | None,
    open_only: bool,
) -> tuple[list[Mission], int]:
    stmt = select(Mission)
    if not auth.scope.tenant_wide:
        stmt = stmt.where(Mission.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        stmt = stmt.where(Mission.site_id == site_id)
    if status is not None:
        stmt = stmt.where(Mission.status == status)
    if vehicle_id is not None:
        stmt = stmt.where(Mission.vehicle_id == vehicle_id)
    if open_only:
        stmt = stmt.where(Mission.status.not_in(TERMINAL))
    total = auth.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = auth.db.execute(
        stmt.order_by(Mission.planned_start.desc(), Mission.mission_id)
        .offset(page.offset)
        .limit(page.page_size)
    )
    return list(rows.scalars()), total


# --- Écritures ------------------------------------------------------------------------------------------


def _assignment_for(auth: Authorized, assignment_id: uuid.UUID, site_id: uuid.UUID | None) -> AssignmentFacts:
    facts = assignment_facts(auth.db, assignment_id)
    if (
        facts is None
        or not auth.scope.covers_site(facts.site_id)
        or (site_id is not None and facts.site_id != site_id)
        or facts.status not in ("PLANNED", "ACTIVE")
    ):
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "vehicle_assignment_id"}])
    return facts


def _active_location(db: Session, location_id: uuid.UUID, site_id: uuid.UUID, field: str) -> SiteLocation:
    location = db.get(SiteLocation, location_id)
    if location is None or location.site_id != site_id or location.status != "ACTIVE":
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": field}])
    return location


def _event(
    auth: Authorized,
    mission: Mission,
    *,
    event_type: str,
    from_status: str | None,
    occurred_at: datetime,
    client_event_id: uuid.UUID | None,
    reason: str | None,
) -> None:
    auth.db.add(
        MissionEvent(
            tenant_id=auth.tenant_id,
            mission_id=mission.mission_id,
            vehicle_assignment_id=mission.vehicle_assignment_id,
            event_type=event_type,
            from_status=from_status,
            to_status=mission.status,
            occurred_at=occurred_at,
            source="DISPATCHER",
            client_event_id=client_event_id,
            actor_user_id=auth.user_id,
            reason=reason,
        )
    )


def create_mission(auth: Authorized, body: MissionCreate) -> MissionOut:
    """US-2.01 : mission « Affectée » sur une affectation planifiée ou active du site (RM-080, RM-082)."""
    db = auth.db
    if body.client_request_id is not None:
        replay = db.execute(
            select(Mission).where(Mission.client_request_id == body.client_request_id)
        ).scalar_one_or_none()
        if replay is not None:
            # Renvoi après coupure réseau (revue L2A-R-08) : la mission déjà créée, sans doublon.
            if (
                not auth.scope.covers_site(replay.site_id)
                or replay.vehicle_assignment_id != body.vehicle_assignment_id
            ):
                raise AppError("CONFLICT")
            out = missions_out(auth, [replay])[0]
            db.commit()
            return out
    facts = _assignment_for(auth, body.vehicle_assignment_id, None)
    if body.origin_location_id == body.destination_location_id:
        raise AppError(
            "VALIDATION_ERROR", details=[{"field": "destination_location_id", "type": "same_as_origin"}]
        )
    _active_location(db, body.origin_location_id, facts.site_id, "origin_location_id")
    _active_location(db, body.destination_location_id, facts.site_id, "destination_location_id")
    material = db.get(Material, body.material_id)
    if material is None or material.status != "ACTIVE":
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "material_id"}])
    if body.due_at is not None and body.due_at <= body.planned_start:
        raise AppError("END_BEFORE_START")
    mission = Mission(
        tenant_id=auth.tenant_id,
        site_id=facts.site_id,
        vehicle_assignment_id=facts.vehicle_assignment_id,
        vehicle_id=facts.vehicle_id,
        driver_id=facts.driver_id,
        origin_location_id=body.origin_location_id,
        destination_location_id=body.destination_location_id,
        material_id=body.material_id,
        planned_start=body.planned_start,
        due_at=body.due_at,
        planned_rotations=body.planned_rotations,
        notes=body.notes,
        client_request_id=body.client_request_id,
        status="ASSIGNED",
        created_by=auth.user_id,
        updated_by=auth.user_id,
    )
    db.add(mission)
    db.flush()
    now = auth.clock.now()
    _event(
        auth,
        mission,
        event_type="CREATED",
        from_status=None,
        occurred_at=now,
        client_event_id=None,
        reason=None,
    )
    record(
        db,
        tenant_id=auth.tenant_id,
        action="mission.create",
        entity_type="mission",
        entity_id=mission.mission_id,
        site_id=mission.site_id,
        actor_user_id=auth.user_id,
        after={"status": mission.status, "vehicle_assignment_id": str(mission.vehicle_assignment_id)},
    )
    db.flush()
    out = missions_out(auth, [mission])[0]
    db.commit()
    return out


def _occurred_at(auth: Authorized, mission: Mission, requested: datetime | None) -> datetime:
    """RM-083 : pas dans le futur (tolérance d'horloge), antidatage borné, ordre chronologique préservé."""
    settings = get_settings()
    now = auth.clock.now()
    at = requested or now
    if at > now + settings.clock_skew_tolerance or at < now - settings.assignment_backdate_tolerance:
        raise AppError("VALIDATION_ERROR", details=[{"field": "occurred_at", "type": "out_of_tolerance"}])
    last = auth.db.execute(
        select(func.max(MissionEvent.occurred_at)).where(MissionEvent.mission_id == mission.mission_id)
    ).scalar_one()
    if last is not None and at < last:
        raise AppError("VALIDATION_ERROR", details=[{"field": "occurred_at", "type": "before_last_event"}])
    return at


def _open_rotation(db: Session, mission: Mission) -> Rotation | None:
    return db.execute(
        select(Rotation).where(Rotation.mission_id == mission.mission_id, Rotation.status == "OPEN")
    ).scalar_one_or_none()


def _ensure_can_run(auth: Authorized, mission: Mission) -> None:
    # Heure serveur, pas l'heure déclarée : un départ antidaté ne contourne pas une échéance (L2A-R-03).
    facts = assignment_facts(auth.db, mission.vehicle_assignment_id)
    reasons = ["REFERENCE_NOT_FOUND"] if facts is None else running_blockers(auth.db, facts, auth.clock.now())
    if reasons:
        raise AppError("MISSION_NOT_ELIGIBLE", details={"reasons": [{"code": r} for r in reasons]})


def _ensure_can_cycle(auth: Authorized, mission: Mission) -> None:
    """Nouveau cycle : affectation encore active et non échue (revue L2A-R-07), plafond de rotations (R-04).

    Le cycle en cours peut se terminer ; ensuite, suspension et réaffectation.
    """
    facts = assignment_facts(auth.db, mission.vehicle_assignment_id)
    now = auth.clock.now()
    reasons = []
    if facts is None or facts.status != "ACTIVE":
        reasons.append("ASSIGNMENT_NOT_ACTIVE")
    elif facts.valid_to is not None and facts.valid_to <= now:
        reasons.append("ASSIGNMENT_ENDED")
    if reasons:
        raise AppError("MISSION_NOT_ELIGIBLE", details={"reasons": [{"code": r} for r in reasons]})
    limit = get_settings().mission_max_rotations
    cycles = auth.db.execute(
        select(func.count()).where(Rotation.mission_id == mission.mission_id, Rotation.status != "ABORTED")
    ).scalar_one()
    if cycles >= limit:
        raise AppError("MISSION_STATE_INVALID", details={"reason": "max_rotations", "limit": limit})


def record_event(
    auth: Authorized, mission_id: uuid.UUID, body: MissionEventCreate, version: int
) -> MissionOut:
    """US-2.02 à US-2.04 : avancement, suspension, reprise, réaffectation, clôture, annulation."""
    db = auth.db
    mission = mission_in_scope(auth, mission_id, for_update=True)
    if body.client_event_id is not None:
        # Recherche limitée à CETTE mission, après le contrôle de portée et sous le verrou : un renvoi
        # concurrent attend le premier puis le reconnaît (L2A-R-06) ; l'identifiant d'une autre mission
        # n'est pas révélé, il échoue sur la contrainte d'unicité comme un conflit ordinaire (L2A-R-05).
        seen = db.execute(
            select(MissionEvent).where(
                MissionEvent.mission_id == mission.mission_id,
                MissionEvent.client_event_id == body.client_event_id,
            )
        ).scalar_one_or_none()
        if seen is not None:
            # Renvoi après coupure réseau (RM-084) : aucun nouvel événement, état courant renvoyé.
            if seen.event_type != body.event_type:
                raise AppError("CONFLICT")
            out = missions_out(auth, [mission], detail=True)[0]
            db.commit()
            return out
    check_version(version, mission.row_version)
    if mission.status in TERMINAL:
        raise AppError("MISSION_STATE_INVALID", details={"status": mission.status})
    at = _occurred_at(auth, mission, body.occurred_at)
    source, kind = mission.status, body.event_type
    reason: str | None = body.reason_code
    rotation = _open_rotation(db, mission)
    if (
        rotation is None
        and kind in ("LOADED", "ARRIVED_UNLOADING", "UNLOADED")
        and source in PROGRESS[kind][0]
    ):
        raise RuntimeError(f"mission {mission.mission_id} en {source} sans rotation ouverte")  # L2A-R-11
    before: dict[str, Any] = {"status": source}
    after: dict[str, Any] = {}
    changed: tuple[str, ...] = ("status",)

    if kind in PROGRESS:
        allowed, target = PROGRESS[kind]
        if source not in allowed:
            raise AppError("MISSION_STATE_INVALID", details={"status": source, "event": kind})
        if kind == "DEPARTED":
            _ensure_can_run(auth, mission)
        if kind == "ARRIVED_LOADING":
            _ensure_can_cycle(auth, mission)
            sequence = (
                db.execute(
                    select(func.max(Rotation.sequence)).where(Rotation.mission_id == mission.mission_id)
                ).scalar_one()
                or 0
            ) + 1
            db.add(
                Rotation(
                    tenant_id=auth.tenant_id,
                    mission_id=mission.mission_id,
                    sequence=sequence,
                    vehicle_id=mission.vehicle_id,
                    driver_id=mission.driver_id,
                    loading_started_at=at,
                )
            )
        elif rotation is not None and kind == "LOADED":
            rotation.loaded_at = at
        elif rotation is not None and kind == "ARRIVED_UNLOADING":
            rotation.unloading_started_at = at
        elif rotation is not None and kind == "UNLOADED":
            rotation.unloaded_at, rotation.status = at, "COMPLETED"
        mission.status = target
    elif kind == "COMPLETED":
        # Fin de mission : au déchargement, ou au retour à vide après au moins une rotation terminée.
        completed = db.execute(
            select(func.count()).where(
                Rotation.mission_id == mission.mission_id, Rotation.status == "COMPLETED"
            )
        ).scalar_one()
        if source == "UNLOADING" and rotation is not None:
            rotation.unloaded_at, rotation.status = at, "COMPLETED"
        elif source != "EN_ROUTE_EMPTY" or completed == 0:
            raise AppError("MISSION_STATE_INVALID", details={"status": source, "event": kind})
        mission.status = "COMPLETED"
    elif kind == "SUSPENDED":
        if source not in SUSPENDABLE:
            raise AppError("MISSION_STATE_INVALID", details={"status": source, "event": kind})
        if reason is None:
            raise AppError("STATUS_REASON_REQUIRED")
        mission.status_before_suspension, mission.status, mission.status_reason = source, "SUSPENDED", reason
    elif kind == "RESUMED":
        if source != "SUSPENDED" or mission.status_before_suspension is None:
            raise AppError("MISSION_STATE_INVALID", details={"status": source, "event": kind})
        target = mission.status_before_suspension
        if target in RUNNING:
            _ensure_can_run(auth, mission)
        mission.status, mission.status_before_suspension, mission.status_reason = target, None, None
    elif kind == "REASSIGNED":
        # US-2.03 : véhicule en panne → autre affectation du même site ; le cycle en cours est perdu.
        if source != "SUSPENDED":
            raise AppError("MISSION_STATE_INVALID", details={"status": source, "event": kind})
        if body.vehicle_assignment_id is None:
            raise AppError(
                "VALIDATION_ERROR", details=[{"field": "vehicle_assignment_id", "type": "missing"}]
            )
        facts = _assignment_for(auth, body.vehicle_assignment_id, mission.site_id)
        if rotation is not None:
            rotation.status = "ABORTED"
        # Qui a pris le relais, et de qui (L2A-R-01) : avant/après dans l'audit, affectation dans l'événement.
        crew = ("vehicle_assignment_id", "vehicle_id", "driver_id")
        before |= {f: str(getattr(mission, f)) for f in crew}
        after |= {f: str(getattr(facts, f)) for f in crew}
        changed = ("status", *crew)
        mission.vehicle_assignment_id = facts.vehicle_assignment_id
        mission.vehicle_id, mission.driver_id = facts.vehicle_id, facts.driver_id
        mission.status_before_suspension = "ASSIGNED"  # reprise depuis le départ, avec le nouvel engin
    elif kind == "CANCELLED":
        if source not in ("PLANNED", "ASSIGNED", "SUSPENDED"):
            raise AppError("MISSION_STATE_INVALID", details={"status": source, "event": kind})
        if reason is None:
            raise AppError("STATUS_REASON_REQUIRED")
        if rotation is not None:
            rotation.status = "ABORTED"
        mission.status, mission.status_reason, mission.status_before_suspension = "CANCELLED", reason, None

    mission.updated_by = auth.user_id
    db.flush()  # contraintes de base (une mission en cours par véhicule/conducteur) vérifiées ici
    _event(
        auth,
        mission,
        event_type=kind,
        from_status=source,
        occurred_at=at,
        client_event_id=body.client_event_id,
        reason=reason,
    )
    record(
        db,
        tenant_id=auth.tenant_id,
        action=f"mission.{kind.lower()}",
        entity_type="mission",
        entity_id=mission.mission_id,
        site_id=mission.site_id,
        actor_user_id=auth.user_id,
        reason=reason,
        before=before,
        after={"status": mission.status, **after},
        changed_fields=changed,
    )
    db.flush()
    out = missions_out(auth, [mission], detail=True)[0]
    db.commit()
    return out
