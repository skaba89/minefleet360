"""Pesées et indicateurs (lot 2b, docs/PLAN_LOT2.md §7).

- Un ticket se rattache à une rotation chargée d'une mission du site ; au plus un ticket non annulé par
  rotation, contrôlé sous le verrou de la rotation (RM-090, RM-091).
- Les tickets et décisions sont en AJOUT SEUL : une correction annule l'original et crée un ticket qui le
  référence, dans la même transaction (RM-073). Le net est calculé par la base.
- Une saisie dégradée ne compte comme mesurée qu'après approbation par une autre personne (RM-075).
- Les indicateurs séparent mesuré, en attente et estimé, sans jamais les additionner (RM-072).
"""

import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, exists, func, literal, or_, select
from sqlalchemy.orm import Session

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.http import PageParams
from app.core.logging import security_logger
from app.dispatch.models import (
    Material,
    Mission,
    MissionEvent,
    Rotation,
    SiteLocation,
    WeighingTicket,
    WeighingTicketDecision,
)
from app.dispatch.schemas import (
    IndicatorRow,
    IndicatorsOut,
    WeighingCorrection,
    WeighingCreate,
    WeighingDecisionOut,
    WeighingFields,
    WeighingOut,
)
from app.fleet.contracts import vehicle_facts

T = WeighingTicket
D = WeighingTicketDecision


def _decided(decision: str) -> Any:
    return exists().where(
        D.tenant_id == T.tenant_id, D.weighing_ticket_id == T.weighing_ticket_id, D.decision == decision
    )


VOIDED = _decided("VOIDED")
APPROVED = _decided("APPROVED")
# Statut dérivé (PLAN_LOT2 §7.1) : annulé, sinon en attente pour une saisie dégradée non approuvée.
STATUS = case(
    (VOIDED, literal("VOIDED")),
    (and_(T.source == "MANUAL_DEGRADED", ~APPROVED), literal("PENDING_APPROVAL")),
    else_=literal("VALID"),
)


# --- Lecture -------------------------------------------------------------------------------------------


def _status(ticket: WeighingTicket, decisions: list[WeighingTicketDecision]) -> str:
    kinds = {d.decision for d in decisions}
    if "VOIDED" in kinds:
        return "VOIDED"
    if ticket.source == "MANUAL_DEGRADED" and "APPROVED" not in kinds:
        return "PENDING_APPROVAL"
    return "VALID"


def tickets_out(auth: Authorized, tickets: list[WeighingTicket]) -> list[WeighingOut]:
    if not tickets:
        return []
    db = auth.db
    ids = [t.weighing_ticket_id for t in tickets]
    decisions: dict[uuid.UUID, list[WeighingTicketDecision]] = defaultdict(list)
    for d in db.execute(select(D).where(D.weighing_ticket_id.in_(ids)).order_by(D.decided_at)).scalars():
        decisions[d.weighing_ticket_id].append(d)
    replaced_by = dict(
        db.execute(
            select(T.replaces_ticket_id, T.weighing_ticket_id).where(T.replaces_ticket_id.in_(ids))
        ).all()
    )
    sequences = dict(
        db.execute(
            select(Rotation.rotation_id, Rotation.sequence).where(
                Rotation.rotation_id.in_({t.rotation_id for t in tickets})
            )
        ).all()
    )
    materials = dict(
        db.execute(
            select(Mission.mission_id, Material.name)
            .join(Material, Material.material_id == Mission.material_id)
            .where(Mission.mission_id.in_({t.mission_id for t in tickets}))
        ).all()
    )
    places = dict(
        db.execute(
            select(SiteLocation.site_location_id, SiteLocation.name).where(
                SiteLocation.site_location_id.in_({t.weighbridge_location_id for t in tickets})
            )
        ).all()
    )
    fleet = vehicle_facts(db, {t.vehicle_id for t in tickets})
    return [
        WeighingOut(
            weighing_ticket_id=t.weighing_ticket_id,
            site_id=t.site_id,
            mission_id=t.mission_id,
            rotation_id=t.rotation_id,
            rotation_sequence=sequences.get(t.rotation_id, 0),
            vehicle_id=t.vehicle_id,
            vehicle_fleet_number=fleet[t.vehicle_id].fleet_number if t.vehicle_id in fleet else "?",
            material_name=materials.get(t.mission_id, "?"),
            weighbridge_location_id=t.weighbridge_location_id,
            weighbridge_name=places.get(t.weighbridge_location_id, "?"),
            ticket_number=t.ticket_number,
            source=t.source,
            degraded_reason=t.degraded_reason,
            weighed_at=t.weighed_at,
            gross_kg=t.gross_kg,
            tare_kg=t.tare_kg,
            net_kg=t.net_kg,
            rated_payload_kg=t.rated_payload_kg,
            overload=t.overload,
            status=_status(t, decisions[t.weighing_ticket_id]),
            replaces_ticket_id=t.replaces_ticket_id,
            replaced_by_ticket_id=replaced_by.get(t.weighing_ticket_id),
            recorded_by=t.recorded_by,
            recorded_at=t.recorded_at,
            decisions=[
                WeighingDecisionOut(
                    decision=d.decision, reason=d.reason, decided_by=d.decided_by, decided_at=d.decided_at
                )
                for d in decisions[t.weighing_ticket_id]
            ],
        )
        for t in tickets
    ]


def ticket_in_scope(auth: Authorized, ticket_id: uuid.UUID) -> WeighingTicket:
    ticket = auth.db.execute(select(T).where(T.weighing_ticket_id == ticket_id)).scalar_one_or_none()
    if ticket is None or not auth.scope.covers_site(ticket.site_id):
        security_logger.info(
            "item_not_found", extra={"entity_type": "weighing_ticket", "entity_id": str(ticket_id)}
        )
        raise AppError("NOT_FOUND")
    return ticket


def list_tickets(
    auth: Authorized,
    page: PageParams,
    *,
    site_id: uuid.UUID | None,
    mission_id: uuid.UUID | None,
    status: str | None,
    overload: bool | None,
    live_only: bool = False,
    period_start: datetime | None,
    period_end: datetime | None,
) -> tuple[list[WeighingTicket], int]:
    stmt = select(T)
    if not auth.scope.tenant_wide:
        stmt = stmt.where(T.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        stmt = stmt.where(T.site_id == site_id)
    if mission_id is not None:
        stmt = stmt.where(T.mission_id == mission_id)
    if status is not None:
        stmt = stmt.where(STATUS == status)
    if live_only:
        stmt = stmt.where(~VOIDED)
    if overload is not None:
        stmt = stmt.where(T.overload.is_(overload))
    if period_start is not None:
        stmt = stmt.where(T.weighed_at >= period_start)
    if period_end is not None:
        stmt = stmt.where(T.weighed_at < period_end)
    total = auth.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = auth.db.execute(
        stmt.order_by(T.weighed_at.desc(), T.weighing_ticket_id).offset(page.offset).limit(page.page_size)
    )
    return list(rows.scalars()), total


# --- Écritures ----------------------------------------------------------------------------------------


def _rotation_in_scope(auth: Authorized, rotation_id: uuid.UUID) -> tuple[Rotation, Mission]:
    """Rotation et mission dans la portée de l'appelant ; lecture SANS verrou (revue L2B-R-06)."""
    found = auth.db.execute(
        select(Rotation, Mission)
        .join(Mission, Mission.mission_id == Rotation.mission_id)
        .where(Rotation.rotation_id == rotation_id)
    ).one_or_none()
    if found is None or not auth.scope.covers_site(found[1].site_id):
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "rotation_id"}])
    return found[0], found[1]


def _lock_rotation(auth: Authorized, rotation_id: uuid.UUID) -> Rotation:
    """Verrou de la rotation : pesées et décisions d'une rotation sérialisées (RM-091), état relu."""
    return auth.db.execute(
        select(Rotation)
        .where(Rotation.rotation_id == rotation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()


def _ensure_weighable(rotation: Rotation) -> None:
    # RM-090 : une rotation chargée, terminée ou en cours, jamais abandonnée.
    if rotation.status == "ABORTED" or (rotation.status == "OPEN" and rotation.loaded_at is None):
        raise AppError("ROTATION_NOT_WEIGHABLE", details={"rotation_status": rotation.status})


def _live_ticket(db: Session, rotation_id: uuid.UUID) -> WeighingTicket | None:
    return db.execute(select(T).where(T.rotation_id == rotation_id, ~VOIDED)).scalars().first()


def _number_taken(db: Session, bridge: uuid.UUID, number: str, *, except_id: uuid.UUID | None = None) -> bool:
    """Numéro porté par une pesée NON ANNULÉE du pont, correctifs compris (revue L2B-R-01)."""
    stmt = select(T.weighing_ticket_id).where(
        T.weighbridge_location_id == bridge, T.ticket_number == number, ~VOIDED
    )
    if except_id is not None:
        stmt = stmt.where(T.weighing_ticket_id != except_id)
    return db.execute(stmt.limit(1)).first() is not None


def _check_bridge(auth: Authorized, bridge_id: uuid.UUID, site_id: uuid.UUID) -> None:
    weighbridge = auth.db.get(SiteLocation, bridge_id)
    if (
        weighbridge is None
        or weighbridge.site_id != site_id
        or weighbridge.kind != "WEIGHBRIDGE"
        or weighbridge.status != "ACTIVE"
    ):
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "weighbridge_location_id"}])


def _check_fields(auth: Authorized, body: WeighingFields, rotation: Rotation, *, correction: bool) -> None:
    settings = get_settings()
    if (body.source == "MANUAL_DEGRADED") != (body.degraded_reason is not None):
        raise AppError("VALIDATION_ERROR", details=[{"field": "degraded_reason", "type": "source_mismatch"}])
    if body.gross_kg <= body.tare_kg:
        raise AppError("VALIDATION_ERROR", details=[{"field": "gross_kg", "type": "not_above_tare"}])
    # RM-093 : pas dans le futur, pas avant le chargement ; antidatage borné, plus largement pour une
    # correction (revue L2B-R-12), sans jamais rouvrir sans limite une période ancienne.
    now = auth.clock.now()
    loaded = rotation.loaded_at or rotation.loading_started_at
    window = (
        settings.weighing_correction_backdate_tolerance
        if correction
        else settings.weighing_backdate_tolerance
    )
    if (
        body.weighed_at > now + settings.clock_skew_tolerance
        or body.weighed_at < loaded - settings.clock_skew_tolerance
        or body.weighed_at < now - window
    ):
        raise AppError("VALIDATION_ERROR", details=[{"field": "weighed_at", "type": "out_of_tolerance"}])


def _new_ticket(
    auth: Authorized,
    body: WeighingFields,
    rotation: Rotation,
    mission: Mission,
    *,
    replaces: uuid.UUID | None,
) -> WeighingTicket:
    rated = None
    facts = vehicle_facts(auth.db, [rotation.vehicle_id]).get(rotation.vehicle_id)
    if facts is not None:
        rated = facts.rated_payload_kg
    net = body.gross_kg - body.tare_kg
    ticket = WeighingTicket(
        tenant_id=auth.tenant_id,
        site_id=mission.site_id,
        mission_id=mission.mission_id,
        rotation_id=rotation.rotation_id,
        vehicle_id=rotation.vehicle_id,
        weighbridge_location_id=body.weighbridge_location_id,
        ticket_number=body.ticket_number,
        source=body.source,
        degraded_reason=body.degraded_reason,
        weighed_at=body.weighed_at,
        gross_kg=body.gross_kg,
        tare_kg=body.tare_kg,
        rated_payload_kg=rated,
        # RM-076 : alerte au-delà de la capacité nominale × seuil (comparaison entière, sans arrondi).
        overload=rated is not None and net * 100 > rated * get_settings().payload_alert_percent,
        replaces_ticket_id=replaces,
        recorded_by=auth.user_id,
    )
    auth.db.add(ticket)
    auth.db.flush()
    return ticket


TRACED = (
    "rotation_id",
    "weighbridge_location_id",
    "ticket_number",
    "source",
    "weighed_at",
    "gross_kg",
    "tare_kg",
)
COMPARED = (
    "weighbridge_location_id",
    "ticket_number",
    "source",
    "degraded_reason",
    "weighed_at",
    "gross_kg",
    "tare_kg",
)


def _values(ticket: WeighingTicket) -> dict[str, Any]:
    """Valeurs tracées dans l'audit (revue L2B-R-10) : aucune donnée personnelle."""
    values: dict[str, Any] = {f: getattr(ticket, f) for f in TRACED}
    values |= {"net_kg": ticket.net_kg, "overload": ticket.overload}
    return {k: str(v) if isinstance(v, (uuid.UUID, datetime)) else v for k, v in values.items()}


def _audit(auth: Authorized, action: str, ticket: WeighingTicket, **extra: Any) -> None:
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        action=action,
        entity_type="weighing_ticket",
        entity_id=ticket.weighing_ticket_id,
        site_id=ticket.site_id,
        actor_user_id=auth.user_id,
        **extra,
    )


def _same(ticket: WeighingTicket, body: WeighingFields, rotation_id: uuid.UUID) -> bool:
    """Renvoi identique (RM-074) : toutes les valeurs saisies concordent."""
    return ticket.rotation_id == rotation_id and all(getattr(ticket, f) == getattr(body, f) for f in COMPARED)


def record_ticket(auth: Authorized, body: WeighingCreate) -> tuple[WeighingOut, bool]:
    """US-2.05 : pesée d'une rotation. Renvoie (ticket, créé) ; un renvoi identique rend le même ticket."""
    db = auth.db
    rotation, mission = _rotation_in_scope(auth, body.rotation_id)
    _check_bridge(auth, body.weighbridge_location_id, mission.site_id)
    rotation = _lock_rotation(auth, rotation.rotation_id)
    existing = db.execute(
        select(T).where(
            T.weighbridge_location_id == body.weighbridge_location_id,
            T.ticket_number == body.ticket_number,
            T.replaces_ticket_id.is_(None),
        )
    ).scalar_one_or_none()
    if existing is not None:
        # RM-074 : renvoi tardif (même hors délai, revue L2B-R-08) → même ticket ; sinon conflit.
        if _same(existing, body, body.rotation_id):
            out = tickets_out(auth, [existing])[0]
            db.commit()
            return out, False
        raise AppError("DUPLICATE_TICKET_NUMBER")
    _ensure_weighable(rotation)
    _check_fields(auth, body, rotation, correction=False)
    if _number_taken(db, body.weighbridge_location_id, body.ticket_number):
        raise AppError("DUPLICATE_TICKET_NUMBER")
    if _live_ticket(db, rotation.rotation_id) is not None:
        raise AppError("ROTATION_ALREADY_WEIGHED")
    ticket = _new_ticket(auth, body, rotation, mission, replaces=None)
    _audit(auth, "weighing_ticket.create", ticket, after=_values(ticket))
    out = tickets_out(auth, [ticket])[0]
    db.commit()
    return out, True


def _decide(auth: Authorized, ticket: WeighingTicket, decision: str, reason: str | None) -> None:
    auth.db.add(
        WeighingTicketDecision(
            tenant_id=auth.tenant_id,
            weighing_ticket_id=ticket.weighing_ticket_id,
            decision=decision,
            reason=reason,
            decided_by=auth.user_id,
        )
    )
    auth.db.flush()


def _ticket_status(db: Session, ticket: WeighingTicket) -> str:
    return _status(
        ticket, list(db.execute(select(D).where(D.weighing_ticket_id == ticket.weighing_ticket_id)).scalars())
    )


def _chain_people(db: Session, ticket: WeighingTicket) -> set[uuid.UUID]:
    """Toutes les personnes ayant saisi ou décidé sur la chaîne des correctifs (revue L2B-R-03)."""
    people: set[uuid.UUID] = set()
    current: WeighingTicket | None = ticket
    for _ in range(100):  # garde-fou : la chaîne ne peut pas boucler (FK, CHECK, un correctif par ticket)
        if current is None:
            break
        people.add(current.recorded_by)
        people |= set(
            db.execute(
                select(D.decided_by).where(D.weighing_ticket_id == current.weighing_ticket_id)
            ).scalars()
        )
        current = db.get(T, current.replaces_ticket_id) if current.replaces_ticket_id else None
    return people


def approve(auth: Authorized, ticket_id: uuid.UUID) -> WeighingOut:
    """RM-075 : une saisie dégradée devient mesurée après approbation par une AUTRE personne."""
    db = auth.db
    ticket = ticket_in_scope(auth, ticket_id)
    _lock_rotation(auth, ticket.rotation_id)
    status = _ticket_status(db, ticket)
    if status != "PENDING_APPROVAL":
        raise AppError("WEIGHING_STATE_INVALID", details={"status": status})
    if auth.user_id in _chain_people(db, ticket):
        raise AppError("SELF_APPROVAL_FORBIDDEN")
    _decide(auth, ticket, "APPROVED", None)
    _audit(
        auth,
        "weighing_ticket.approve",
        ticket,
        before={"status": status},
        after={"status": "VALID", "net_kg": ticket.net_kg, "approved_by": str(auth.user_id)},
    )
    out = tickets_out(auth, [ticket])[0]
    db.commit()
    return out


def void(auth: Authorized, ticket_id: uuid.UUID, reason: str) -> WeighingOut:
    db = auth.db
    ticket = ticket_in_scope(auth, ticket_id)
    _lock_rotation(auth, ticket.rotation_id)
    status = _ticket_status(db, ticket)
    if status == "VOIDED":
        raise AppError("WEIGHING_STATE_INVALID", details={"status": "VOIDED"})
    _decide(auth, ticket, "VOIDED", reason)
    _audit(
        auth,
        "weighing_ticket.void",
        ticket,
        reason=reason,
        before={"status": status},
        after={"status": "VOIDED"},
    )
    out = tickets_out(auth, [ticket])[0]
    db.commit()
    return out


def correct(auth: Authorized, ticket_id: uuid.UUID, body: WeighingCorrection) -> tuple[WeighingOut, bool]:
    """US-2.06 : annulation de l'original et ticket correctif qui le référence, dans la même transaction.

    Renvoie (correctif, créé) : un renvoi identique après coupure réseau rend le même correctif (L2B-R-09).
    """
    db = auth.db
    original = ticket_in_scope(auth, ticket_id)
    target, mission = _rotation_in_scope(auth, body.rotation_id or original.rotation_id)
    _check_bridge(auth, body.weighbridge_location_id, mission.site_id)
    # Verrous dans un ordre stable : pas d'interblocage entre deux corrections croisées.
    for rotation_id in sorted({original.rotation_id, target.rotation_id}):
        locked = _lock_rotation(auth, rotation_id)
        if rotation_id == target.rotation_id:
            target = locked
    status = _ticket_status(db, original)
    if status == "VOIDED":
        replacement = db.execute(
            select(T).where(T.replaces_ticket_id == original.weighing_ticket_id)
        ).scalar_one_or_none()
        if replacement is not None and _same(replacement, body, target.rotation_id):
            out = tickets_out(auth, [replacement])[0]
            db.commit()
            return out, False
        raise AppError("WEIGHING_STATE_INVALID", details={"status": "VOIDED"})
    # Revue L2B-R-02 : une saisie dégradée ne devient pas « pont-bascule » par correction ; il faut
    # l'annuler et saisir le vrai ticket du pont, ou la faire approuver.
    if original.source == "MANUAL_DEGRADED" and body.source == "WEIGHBRIDGE":
        raise AppError("VALIDATION_ERROR", details=[{"field": "source", "type": "degraded_to_weighbridge"}])
    _ensure_weighable(target)
    _check_fields(auth, body, target, correction=True)
    if _number_taken(
        db, body.weighbridge_location_id, body.ticket_number, except_id=original.weighing_ticket_id
    ):
        raise AppError("DUPLICATE_TICKET_NUMBER")
    _decide(auth, original, "VOIDED", body.reason_code)
    _audit(
        auth,
        "weighing_ticket.void",
        original,
        reason=body.reason_code,
        before={"status": status},
        after={"status": "VOIDED", "by_correction": True},
    )
    if _live_ticket(db, target.rotation_id) is not None:
        raise AppError("ROTATION_ALREADY_WEIGHED")
    ticket = _new_ticket(auth, body, target, mission, replaces=original.weighing_ticket_id)
    before, after = _values(original), _values(ticket)
    _audit(
        auth,
        "weighing_ticket.correct",
        ticket,
        reason=body.reason_code,
        before={"weighing_ticket_id": str(original.weighing_ticket_id), **before},
        after=after,
        changed_fields=tuple(sorted(k for k in after if after[k] != before.get(k))),
    )
    out = tickets_out(auth, [ticket])[0]
    db.commit()
    return out, True


# --- Indicateurs (US-2.08) ----------------------------------------------------------------------------


def indicators(
    auth: Authorized,
    *,
    site_id: uuid.UUID | None,
    period_start: datetime | None,
    period_end: datetime | None,
) -> IndicatorsOut:
    settings = get_settings()
    end = period_end or auth.clock.now()
    start = period_start or end - timedelta(days=7)
    if start >= end or end - start > settings.indicators_max_period:
        raise AppError("VALIDATION_ERROR", details=[{"field": "period_start", "type": "invalid_period"}])
    db = auth.db

    def scoped(stmt: Any) -> Any:
        if not auth.scope.tenant_wide:
            stmt = stmt.where(Mission.site_id.in_(auth.scope.site_ids))
        if site_id is not None:
            stmt = stmt.where(Mission.site_id == site_id)
        return stmt

    # Revue L2B-R-11 : seules les pesées des rotations terminées sur la période sont lues.
    period_rotations = select(Rotation.rotation_id).where(
        Rotation.status == "COMPLETED", Rotation.unloaded_at >= start, Rotation.unloaded_at < end
    )
    live = (
        select(
            T.rotation_id,
            T.net_kg,
            T.overload,
            case(
                (or_(T.source == "WEIGHBRIDGE", APPROVED), literal("VALID")), else_=literal("PENDING")
            ).label("state"),
        )
        .where(~VOIDED, T.rotation_id.in_(period_rotations))
        .subquery()
    )
    cycle = func.extract("epoch", Rotation.unloaded_at - Rotation.loading_started_at)
    valid = live.c.state == "VALID"
    pending = live.c.state == "PENDING"
    rows = db.execute(
        scoped(
            select(
                Mission.site_id,
                Mission.material_id,
                Rotation.vehicle_id,
                func.count().label("rotations"),
                func.sum(cycle).label("cycle_total"),
                func.count().filter(cycle < settings.rotation_min_cycle.total_seconds()).label("short"),
                func.coalesce(func.sum(live.c.net_kg).filter(valid), 0).label("measured_kg"),
                func.count().filter(valid).label("measured"),
                func.coalesce(func.sum(live.c.net_kg).filter(pending), 0).label("pending_kg"),
                func.count().filter(pending).label("pending"),
                func.count().filter(live.c.rotation_id.is_(None)).label("unweighed"),
                func.count().filter(live.c.overload.is_(True)).label("overload"),
            )
            .join(Mission, Mission.mission_id == Rotation.mission_id)
            .outerjoin(live, live.c.rotation_id == Rotation.rotation_id)
            .where(Rotation.status == "COMPLETED", Rotation.unloaded_at >= start, Rotation.unloaded_at < end)
            .group_by(Mission.site_id, Mission.material_id, Rotation.vehicle_id)
        )
    ).all()
    missions = db.execute(
        scoped(
            select(Mission.site_id, Mission.material_id, func.count(func.distinct(Mission.mission_id)))
            .join(MissionEvent, MissionEvent.mission_id == Mission.mission_id)
            .where(
                MissionEvent.event_type == "COMPLETED",
                MissionEvent.occurred_at >= start,
                MissionEvent.occurred_at < end,
            )
            .group_by(Mission.site_id, Mission.material_id)
        )
    ).all()
    rated = {v: f.rated_payload_kg for v, f in vehicle_facts(db, {r.vehicle_id for r in rows}).items()}
    acc: dict[tuple[uuid.UUID, uuid.UUID], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        a = acc[(r.site_id, r.material_id)]
        a["rotations"] += r.rotations
        a["cycle_total"] += float(r.cycle_total or 0)
        for key in ("short", "measured_kg", "measured", "pending_kg", "pending", "overload"):
            a[key] += getattr(r, key)
        payload = rated.get(r.vehicle_id)
        # RM-072 : estimation séparée, uniquement pour les rotations sans aucune pesée.
        if payload:
            a["estimated_kg"] += payload * r.unweighed
            a["estimated"] += r.unweighed
        else:
            a["no_estimate"] += r.unweighed
    for site, material, count in missions:
        acc[(site, material)]["missions"] += count
    names = dict(
        db.execute(
            select(Material.material_id, Material.name).where(Material.material_id.in_({m for _, m in acc}))
        ).all()
    )
    out = [
        IndicatorRow(
            site_id=site,
            material_id=material,
            material_name=names.get(material, "?"),
            missions_completed=int(a["missions"]),
            rotations_completed=int(a["rotations"]),
            avg_cycle_seconds=round(a["cycle_total"] / a["rotations"]) if a["rotations"] else None,
            short_cycles=int(a["short"]),
            measured_net_kg=int(a["measured_kg"]),
            measured_rotations=int(a["measured"]),
            pending_net_kg=int(a["pending_kg"]),
            pending_rotations=int(a["pending"]),
            estimated_kg=int(a["estimated_kg"]),
            estimated_rotations=int(a["estimated"]),
            rotations_without_estimate=int(a["no_estimate"]),
            overload_tickets=int(a["overload"]),
        )
        for (site, material), a in acc.items()
    ]
    out.sort(key=lambda row: (str(row.site_id), row.material_name))
    return IndicatorsOut(period_start=start, period_end=end, rows=out)
