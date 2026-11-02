"""Incidents HSE et actions correctives (lot HSE-1, docs/LIVRAISON_HSE1.md).

- Cycle de l'incident : REPORTED → INVESTIGATING → CLOSED, ou CANCELLED avec motif codé. Chaque transition et
  chaque étape d'action écrit un événement en ajout seul et un audit, dans la même transaction ; concurrence
  par If-Match.
- Clôture : cause racine renseignée, toutes les actions vérifiées ou annulées, au moins une action vérifiée
  pour un incident grave, et par une autre personne que le déclarant (séparation des tâches).
- Action corrective : réalisée par son responsable seulement, vérifiée par une autre personne.
- Verrous toujours dans l'ordre incident → action (pas d'interblocage entre clôture et réalisation).
- Données personnelles minimales : nombre de blessés, jamais leur identité ni de donnée médicale.
"""

import uuid
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select, text

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.core.http import PageParams, check_version
from app.core.logging import security_logger
from app.fleet.contracts import vehicle_facts
from app.hse.models import HseCorrectiveAction, HseIncident, HseIncidentEvent
from app.hse.schemas import (
    ActionComplete,
    ActionCreate,
    ActionDecisionIn,
    ActionOut,
    ActionOwnerOut,
    EventOut,
    HseSummaryOut,
    IncidentCreate,
    IncidentOut,
    IncidentTransition,
)
from app.identity.contracts import display_names, users_with_roles
from app.organization.contracts import active_site_in_scope, local_date

OPEN_INCIDENT = frozenset({"REPORTED", "INVESTIGATING"})
SETTLED_ACTION = frozenset({"VERIFIED", "CANCELLED"})
# Rôles pouvant porter une action corrective (ils détiennent hse.action.complete dans la matrice).
ACTION_OWNER_ROLES = ("OPS_MANAGER", "DISPATCHER", "WORKSHOP_CHIEF", "HSE")
SERIOUS = frozenset({"HIGH", "CRITICAL"})
# Tolérance de décalage d'horloge d'un terminal de terrain (même borne que ck_hsei_occurred).
CLOCK_SKEW = timedelta(minutes=10)


def reference(number: int) -> str:
    return f"HSE-{number:06d}"


# --- Lecture -------------------------------------------------------------------------------------------


class _Today:
    """Date locale du jour par site (échéances évaluées dans le fuseau du site, pas en UTC)."""

    def __init__(self, auth: Authorized) -> None:
        self._auth = auth
        self._now = auth.clock.now()
        self._cache: dict[uuid.UUID, date] = {}

    def __call__(self, site_id: uuid.UUID) -> date:
        if site_id not in self._cache:
            self._cache[site_id] = local_date(self._auth.db, site_id, self._now)
        return self._cache[site_id]


def _overdue(action: HseCorrectiveAction, today: _Today) -> bool:
    return action.status == "OPEN" and action.due_date < today(action.site_id)


def actions_out(
    auth: Authorized, actions: list[HseCorrectiveAction], numbers: dict[uuid.UUID, int] | None = None
) -> list[ActionOut]:
    if not actions:
        return []
    db = auth.db
    if numbers is None:
        numbers = dict(
            db.execute(
                select(HseIncident.hse_incident_id, HseIncident.number).where(
                    HseIncident.hse_incident_id.in_({a.hse_incident_id for a in actions})
                )
            ).all()
        )
    names = display_names(db, {a.owner_user_id for a in actions})
    today = _Today(auth)
    return [
        ActionOut(
            hse_corrective_action_id=a.hse_corrective_action_id,
            hse_incident_id=a.hse_incident_id,
            incident_reference=reference(numbers[a.hse_incident_id]),
            site_id=a.site_id,
            title=a.title,
            description=a.description,
            owner_user_id=a.owner_user_id,
            owner_name=names.get(a.owner_user_id),
            due_date=a.due_date,
            overdue=_overdue(a, today),
            status=a.status,
            status_reason=a.status_reason,
            completion_note=a.completion_note,
            completed_at=a.completed_at,
            completed_by=a.completed_by,
            verified_at=a.verified_at,
            verified_by=a.verified_by,
            row_version=a.row_version,
        )
        for a in actions
    ]


def incidents_out(
    auth: Authorized, incidents: list[HseIncident], *, detail: bool = False
) -> list[IncidentOut]:
    if not incidents:
        return []
    db = auth.db
    ids = [i.hse_incident_id for i in incidents]
    fleet = vehicle_facts(db, {i.vehicle_id for i in incidents if i.vehicle_id})
    actions: dict[uuid.UUID, list[HseCorrectiveAction]] = defaultdict(list)
    for action in db.execute(
        select(HseCorrectiveAction)
        .where(HseCorrectiveAction.hse_incident_id.in_(ids))
        .order_by(HseCorrectiveAction.due_date, HseCorrectiveAction.created_at)
    ).scalars():
        actions[action.hse_incident_id].append(action)
    events: dict[uuid.UUID, list[HseIncidentEvent]] = defaultdict(list)
    people = {i.reported_by for i in incidents}
    if detail:
        for e in db.execute(
            select(HseIncidentEvent)
            .where(HseIncidentEvent.hse_incident_id.in_(ids))
            .order_by(HseIncidentEvent.occurred_at, HseIncidentEvent.hse_incident_event_id)
        ).scalars():
            events[e.hse_incident_id].append(e)
            people.add(e.actor_user_id)
    names = display_names(db, people)
    today = _Today(auth)
    numbers = {i.hse_incident_id: i.number for i in incidents}
    out = []
    for i in incidents:
        own = actions[i.hse_incident_id]
        data: dict[str, Any] = {
            "hse_incident_id": i.hse_incident_id,
            "number": i.number,
            "reference": reference(i.number),
            "site_id": i.site_id,
            "category": i.category,
            "severity": i.severity,
            "title": i.title,
            "description": i.description,
            "occurred_at": i.occurred_at,
            "location_note": i.location_note,
            "vehicle_id": i.vehicle_id,
            "vehicle_fleet_number": fleet[i.vehicle_id].fleet_number
            if i.vehicle_id and i.vehicle_id in fleet
            else None,
            "injured_count": i.injured_count,
            "lost_time": i.lost_time,
            "immediate_actions": i.immediate_actions,
            "status": i.status,
            "status_reason": i.status_reason,
            "root_cause": i.root_cause,
            "investigation_summary": i.investigation_summary,
            "reported_at": i.reported_at,
            "reported_by": i.reported_by,
            "reported_by_name": names.get(i.reported_by),
            "closed_at": i.closed_at,
            "closed_by": i.closed_by,
            "open_actions": sum(1 for a in own if a.status in ("OPEN", "DONE")),
            "overdue_actions": sum(1 for a in own if _overdue(a, today)),
            "row_version": i.row_version,
        }
        if detail:
            data["events"] = [
                EventOut(
                    event_type=e.event_type,
                    from_status=e.from_status,
                    to_status=e.to_status,
                    reason=e.reason,
                    actor_user_id=e.actor_user_id,
                    actor_name=names.get(e.actor_user_id),
                    occurred_at=e.occurred_at,
                )
                for e in events[i.hse_incident_id]
            ]
            data["actions"] = actions_out(auth, own, numbers)
        out.append(IncidentOut(**data))
    return out


def _scoped(auth: Authorized, column: Any, site_id: uuid.UUID | None) -> list[Any]:
    if site_id is not None and not auth.scope.covers_site(site_id):
        raise AppError("NOT_FOUND")
    conditions = []
    if not auth.scope.tenant_wide:
        conditions.append(column.in_(auth.scope.site_ids))
    if site_id is not None:
        conditions.append(column == site_id)
    return conditions


def list_incidents(
    auth: Authorized,
    page: PageParams,
    *,
    site_id: uuid.UUID | None,
    status: str | None,
    severity: str | None,
    category: str | None,
    open_only: bool,
) -> tuple[list[HseIncident], int]:
    conditions = _scoped(auth, HseIncident.site_id, site_id)
    if status is not None:
        conditions.append(HseIncident.status == status)
    if severity is not None:
        conditions.append(HseIncident.severity == severity)
    if category is not None:
        conditions.append(HseIncident.category == category)
    if open_only:
        conditions.append(HseIncident.status.in_(OPEN_INCIDENT))
    total = auth.db.execute(select(func.count()).select_from(HseIncident).where(*conditions)).scalar_one()
    rows = (
        auth.db.execute(
            select(HseIncident)
            .where(*conditions)
            .order_by(HseIncident.occurred_at.desc(), HseIncident.number.desc())
            .offset(page.offset)
            .limit(page.page_size)
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


def incident_in_scope(auth: Authorized, incident_id: uuid.UUID, *, for_update: bool = False) -> HseIncident:
    stmt = select(HseIncident).where(HseIncident.hse_incident_id == incident_id)
    incident = auth.db.execute(stmt).scalar_one_or_none()
    if incident is None or not auth.scope.covers_site(incident.site_id):
        security_logger.info(
            "item_not_found", extra={"entity_type": "hse_incident", "entity_id": str(incident_id)}
        )
        raise AppError("NOT_FOUND")
    if for_update:
        incident = auth.db.execute(
            stmt.with_for_update().execution_options(populate_existing=True)
        ).scalar_one()
    return incident


def action_in_scope(auth: Authorized, action_id: uuid.UUID) -> HseCorrectiveAction:
    action = auth.db.execute(
        select(HseCorrectiveAction).where(HseCorrectiveAction.hse_corrective_action_id == action_id)
    ).scalar_one_or_none()
    if action is None or not auth.scope.covers_site(action.site_id):
        security_logger.info(
            "item_not_found", extra={"entity_type": "hse_corrective_action", "entity_id": str(action_id)}
        )
        raise AppError("NOT_FOUND")
    return action


def list_actions(
    auth: Authorized,
    page: PageParams,
    *,
    site_id: uuid.UUID | None,
    status: str | None,
    mine: bool,
    open_only: bool,
) -> tuple[list[ActionOut], int]:
    conditions = _scoped(auth, HseCorrectiveAction.site_id, site_id)
    if status is not None:
        conditions.append(HseCorrectiveAction.status == status)
    if open_only:
        conditions.append(HseCorrectiveAction.status.in_(("OPEN", "DONE")))
    if mine:
        conditions.append(HseCorrectiveAction.owner_user_id == auth.user_id)
    total = auth.db.execute(
        select(func.count()).select_from(HseCorrectiveAction).where(*conditions)
    ).scalar_one()
    rows = (
        auth.db.execute(
            select(HseCorrectiveAction)
            .where(*conditions)
            .order_by(HseCorrectiveAction.due_date, HseCorrectiveAction.created_at)
            .offset(page.offset)
            .limit(page.page_size)
        )
        .scalars()
        .all()
    )
    return actions_out(auth, list(rows)), int(total)


def action_owners(auth: Authorized, incident_id: uuid.UUID) -> list[ActionOwnerOut]:
    incident = incident_in_scope(auth, incident_id)
    return [
        ActionOwnerOut(user_account_id=user_id, display_name=name)
        for user_id, name in users_with_roles(auth.db, ACTION_OWNER_ROLES, incident.site_id, auth.clock.now())
    ]


def summary(auth: Authorized, *, site_id: uuid.UUID | None, days: int) -> HseSummaryOut:
    """Comptages bruts vérifiables ; pas de taux de fréquence (heures travaillées non disponibles)."""
    db = auth.db
    now = auth.clock.now()
    since = now - timedelta(days=days)
    incident_scope = _scoped(auth, HseIncident.site_id, site_id)
    recent = db.execute(
        select(
            HseIncident.severity, HseIncident.category, HseIncident.injured_count, HseIncident.lost_time
        ).where(*incident_scope, HseIncident.occurred_at >= since, HseIncident.status != "CANCELLED")
    ).all()
    open_incidents = db.execute(
        select(func.count())
        .select_from(HseIncident)
        .where(*incident_scope, HseIncident.status.in_(OPEN_INCIDENT))
    ).scalar_one()
    pending = (
        db.execute(
            select(HseCorrectiveAction).where(
                *_scoped(auth, HseCorrectiveAction.site_id, site_id),
                HseCorrectiveAction.status.in_(("OPEN", "DONE")),
            )
        )
        .scalars()
        .all()
    )
    today = _Today(auth)
    return HseSummaryOut(
        since=since.date(),
        incidents=len(recent),
        by_severity=dict(Counter(r.severity for r in recent)),
        by_category=dict(Counter(r.category for r in recent)),
        injured=sum(r.injured_count for r in recent),
        lost_time_incidents=sum(1 for r in recent if r.lost_time),
        open_incidents=int(open_incidents),
        open_actions=len(pending),
        overdue_actions=sum(1 for a in pending if _overdue(a, today)),
    )


# --- Écriture ------------------------------------------------------------------------------------------


def _event(
    auth: Authorized, incident: HseIncident, event_type: str, source: str | None, reason: str | None
) -> None:
    auth.db.add(
        HseIncidentEvent(
            tenant_id=auth.tenant_id,
            hse_incident_id=incident.hse_incident_id,
            event_type=event_type,
            from_status=source,
            to_status=incident.status,
            reason=reason,
            actor_user_id=auth.user_id,
        )
    )


def _audit(
    auth: Authorized, action: str, entity_type: str, entity_id: uuid.UUID, site_id: uuid.UUID, **extra: Any
) -> None:
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        site_id=site_id,
        actor_user_id=auth.user_id,
        **extra,
    )


def _next_number(auth: Authorized) -> int:
    """Numéro suivant du tenant : incrément atomique sous verrou de ligne (pas de doublon concurrent)."""
    return int(
        auth.db.execute(
            text(
                "INSERT INTO hse_counter (tenant_id, last_number) VALUES (:t, 1) "
                "ON CONFLICT (tenant_id) DO UPDATE SET last_number = hse_counter.last_number + 1 "
                "RETURNING last_number"
            ),
            {"t": str(auth.tenant_id)},
        ).scalar_one()
    )


def _detail(auth: Authorized, incident: HseIncident) -> IncidentOut:
    auth.db.flush()
    return incidents_out(auth, [incident], detail=True)[0]


def report_incident(auth: Authorized, body: IncidentCreate) -> IncidentOut:
    db = auth.db
    if active_site_in_scope(db, auth.scope, body.site_id) is None:
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "site_id"}])
    now = auth.clock.now()
    if body.occurred_at > now + CLOCK_SKEW:
        raise AppError("VALIDATION_ERROR", details=[{"field": "occurred_at", "type": "in_future"}])
    if body.vehicle_id is not None:
        facts = vehicle_facts(db, [body.vehicle_id]).get(body.vehicle_id)
        # Le véhicule doit appartenir au site déclaré : pas de rattachement d'un engin d'un autre périmètre.
        if facts is None or facts.site_id != body.site_id:
            raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "vehicle_id"}])
    incident = HseIncident(
        tenant_id=auth.tenant_id,
        site_id=body.site_id,
        category=body.category,
        severity=body.severity,
        title=body.title,
        description=body.description,
        occurred_at=body.occurred_at,
        location_note=body.location_note or None,
        vehicle_id=body.vehicle_id,
        injured_count=body.injured_count,
        lost_time=body.lost_time,
        immediate_actions=body.immediate_actions or None,
        reported_at=now,
        reported_by=auth.user_id,
        created_by=auth.user_id,
        updated_by=auth.user_id,
        # Numéro pris en dernier : le verrou du compteur du tenant est tenu le moins longtemps.
        number=_next_number(auth),
    )
    db.add(incident)
    db.flush()
    _event(auth, incident, "REPORTED", None, None)
    _audit(
        auth,
        "hse.incident.report",
        "hse_incident",
        incident.hse_incident_id,
        incident.site_id,
        after={
            "reference": reference(incident.number),
            "category": incident.category,
            "severity": incident.severity,
            "injured_count": incident.injured_count,
            "vehicle_id": str(incident.vehicle_id) if incident.vehicle_id else None,
        },
    )
    out = _detail(auth, incident)
    db.commit()
    return out


def _actions_of(auth: Authorized, incident: HseIncident) -> list[HseCorrectiveAction]:
    return list(
        auth.db.execute(
            select(HseCorrectiveAction).where(HseCorrectiveAction.hse_incident_id == incident.hse_incident_id)
        )
        .scalars()
        .all()
    )


def transition(
    auth: Authorized, incident_id: uuid.UUID, body: IncidentTransition, version: int
) -> IncidentOut:
    db = auth.db
    incident = incident_in_scope(auth, incident_id, for_update=True)
    check_version(version, incident.row_version)
    source = incident.status
    edits = {
        k: v
        for k, v in {
            "root_cause": body.root_cause,
            "investigation_summary": body.investigation_summary,
            "severity": body.severity,
            "category": body.category,
        }.items()
        if v is not None
    }
    if edits and body.action not in ("NOTE", "CLOSE"):
        raise AppError("VALIDATION_ERROR", details=[{"field": next(iter(edits)), "type": "not_applicable"}])
    if body.reason_code is not None and body.action != "CANCEL":
        raise AppError("VALIDATION_ERROR", details=[{"field": "reason_code", "type": "not_applicable"}])
    before = {k: getattr(incident, k) for k in edits}
    now = auth.clock.now()
    reason: str | None = None
    if body.action == "START_INVESTIGATION":
        if source != "REPORTED":
            raise AppError("HSE_INCIDENT_STATE_INVALID", details={"status": source, "action": body.action})
        incident.status = "INVESTIGATING"
        event_type = "INVESTIGATION_STARTED"
    elif body.action == "NOTE":
        if source != "INVESTIGATING":
            raise AppError("HSE_INCIDENT_STATE_INVALID", details={"status": source, "action": body.action})
        if not edits:
            raise AppError("VALIDATION_ERROR", details=[{"field": "root_cause", "type": "missing"}])
        event_type = "NOTED"
    elif body.action == "CLOSE":
        if source != "INVESTIGATING":
            raise AppError("HSE_INCIDENT_STATE_INVALID", details={"status": source, "action": body.action})
        if incident.reported_by == auth.user_id:
            raise AppError("HSE_SELF_CLOSURE_FORBIDDEN")
        actions = _actions_of(auth, incident)
        if any(a.status not in SETTLED_ACTION for a in actions):
            raise AppError("HSE_ACTIONS_PENDING")
        severity = edits.get("severity", incident.severity)
        if severity in SERIOUS and not any(a.status == "VERIFIED" for a in actions):
            raise AppError("HSE_CORRECTIVE_ACTION_REQUIRED")
        if not (edits.get("root_cause") or incident.root_cause):
            raise AppError("VALIDATION_ERROR", details=[{"field": "root_cause", "type": "missing"}])
        incident.status = "CLOSED"
        incident.closed_at = now
        incident.closed_by = auth.user_id
        event_type = "CLOSED"
    else:  # CANCEL
        if source not in OPEN_INCIDENT:
            raise AppError("HSE_INCIDENT_STATE_INVALID", details={"status": source, "action": body.action})
        if body.reason_code is None:
            raise AppError("STATUS_REASON_REQUIRED")
        if any(a.status != "CANCELLED" for a in _actions_of(auth, incident)):
            raise AppError("HSE_ACTIONS_PENDING")
        incident.status = "CANCELLED"
        incident.status_reason = body.reason_code
        reason = body.reason_code
        event_type = "CANCELLED"
    for key, value in edits.items():
        setattr(incident, key, value)
    incident.updated_by = auth.user_id
    db.flush()
    _event(auth, incident, event_type, source, reason)
    changed = sorted(edits) + (["status"] if incident.status != source else [])
    _audit(
        auth,
        f"hse.incident.{body.action.lower()}",
        "hse_incident",
        incident.hse_incident_id,
        incident.site_id,
        reason=reason,
        # Textes d'enquête non recopiés dans le journal : seuls les champs modifiés sont tracés.
        before={k: v for k, v in before.items() if k in ("severity", "category")},
        after={k: v for k, v in edits.items() if k in ("severity", "category")} | {"status": incident.status},
        changed_fields=changed,
    )
    out = _detail(auth, incident)
    db.commit()
    return out


def add_action(auth: Authorized, incident_id: uuid.UUID, body: ActionCreate) -> ActionOut:
    db = auth.db
    incident = incident_in_scope(auth, incident_id, for_update=True)
    if incident.status not in OPEN_INCIDENT:
        raise AppError(
            "HSE_INCIDENT_STATE_INVALID", details={"status": incident.status, "action": "ADD_ACTION"}
        )
    eligible = {u for u, _ in users_with_roles(db, ACTION_OWNER_ROLES, incident.site_id, auth.clock.now())}
    if body.owner_user_id not in eligible:
        raise AppError("HSE_OWNER_NOT_ELIGIBLE", details=[{"field": "owner_user_id"}])
    if body.due_date < local_date(db, incident.site_id, auth.clock.now()):
        raise AppError("VALIDATION_ERROR", details=[{"field": "due_date", "type": "in_past"}])
    action = HseCorrectiveAction(
        tenant_id=auth.tenant_id,
        site_id=incident.site_id,
        hse_incident_id=incident.hse_incident_id,
        title=body.title,
        description=body.description or None,
        owner_user_id=body.owner_user_id,
        due_date=body.due_date,
        created_by=auth.user_id,
        updated_by=auth.user_id,
    )
    db.add(action)
    db.flush()
    _event(auth, incident, "ACTION_ADDED", incident.status, None)
    _audit(
        auth,
        "hse.action.create",
        "hse_corrective_action",
        action.hse_corrective_action_id,
        action.site_id,
        after={
            "incident": reference(incident.number),
            "owner_user_id": str(action.owner_user_id),
            "due_date": action.due_date.isoformat(),
        },
    )
    out = actions_out(auth, [action], {incident.hse_incident_id: incident.number})[0]
    db.commit()
    return out


def _locked_action(auth: Authorized, action_id: uuid.UUID) -> tuple[HseIncident, HseCorrectiveAction]:
    """Verrouille l'incident puis l'action (ordre fixe, cf. clôture)."""
    action = action_in_scope(auth, action_id)
    incident = incident_in_scope(auth, action.hse_incident_id, for_update=True)
    locked = auth.db.execute(
        select(HseCorrectiveAction)
        .where(HseCorrectiveAction.hse_corrective_action_id == action_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()
    return incident, locked


def complete_action(auth: Authorized, action_id: uuid.UUID, body: ActionComplete, version: int) -> ActionOut:
    db = auth.db
    incident, action = _locked_action(auth, action_id)
    check_version(version, action.row_version)
    if action.owner_user_id != auth.user_id:
        raise AppError("HSE_NOT_ACTION_OWNER")
    if action.status != "OPEN":
        raise AppError("HSE_ACTION_STATE_INVALID", details={"status": action.status, "action": "COMPLETE"})
    action.status = "DONE"
    action.status_reason = None
    action.completion_note = body.completion_note
    action.completed_at = auth.clock.now()
    action.completed_by = auth.user_id
    action.updated_by = auth.user_id
    db.flush()
    _event(auth, incident, "ACTION_COMPLETED", incident.status, None)
    _audit(
        auth,
        "hse.action.complete",
        "hse_corrective_action",
        action.hse_corrective_action_id,
        action.site_id,
        changed_fields=["status", "completion_note"],
    )
    out = actions_out(auth, [action], {incident.hse_incident_id: incident.number})[0]
    db.commit()
    return out


def decide_action(auth: Authorized, action_id: uuid.UUID, body: ActionDecisionIn, version: int) -> ActionOut:
    db = auth.db
    incident, action = _locked_action(auth, action_id)
    check_version(version, action.row_version)
    source = action.status
    if body.action == "VERIFY":
        if source != "DONE":
            raise AppError("HSE_ACTION_STATE_INVALID", details={"status": source, "action": body.action})
        if action.completed_by == auth.user_id:
            raise AppError("HSE_SELF_VERIFICATION_FORBIDDEN")
        action.status = "VERIFIED"
        action.verified_at = auth.clock.now()
        action.verified_by = auth.user_id
        event_type = "ACTION_VERIFIED"
    elif body.action == "REOPEN":
        if source != "DONE":
            raise AppError("HSE_ACTION_STATE_INVALID", details={"status": source, "action": body.action})
        if body.reason_code is None:
            raise AppError("STATUS_REASON_REQUIRED")
        action.status = "OPEN"
        action.status_reason = body.reason_code
        action.completed_at = None
        action.completed_by = None
        event_type = "ACTION_REOPENED"
    else:  # CANCEL
        if source not in ("OPEN", "DONE"):
            raise AppError("HSE_ACTION_STATE_INVALID", details={"status": source, "action": body.action})
        if body.reason_code is None:
            raise AppError("STATUS_REASON_REQUIRED")
        action.status = "CANCELLED"
        action.status_reason = body.reason_code
        event_type = "ACTION_CANCELLED"
    action.updated_by = auth.user_id
    db.flush()
    _event(auth, incident, event_type, incident.status, body.reason_code)
    _audit(
        auth,
        f"hse.action.{body.action.lower()}",
        "hse_corrective_action",
        action.hse_corrective_action_id,
        action.site_id,
        reason=body.reason_code,
        before={"status": source},
        after={"status": action.status},
    )
    out = actions_out(auth, [action], {incident.hse_incident_id: incident.number})[0]
    db.commit()
    return out
