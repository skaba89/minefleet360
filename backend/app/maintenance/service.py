"""Ordres de travail (lot 3a, docs/PLAN_LOT3.md).

- Cycle de vie strict (MODELE_CONCEPTUEL §4.5) ; chaque transition écrit un événement en ajout seul et
  un audit, dans la même transaction ; concurrence par If-Match.
- Effets sur l'exploitation (D-44) : panne bloquante → véhicule immobilisé et mission en cours suspendue ;
  début d'intervention → véhicule en maintenance ; clôture conforme → véhicule disponible si aucun autre
  OT ne le retient. Les changements de statut passent par le contrat fleet (mêmes règles qu'à la main).
- Séparation des tâches : la remise en service est faite par une autre personne que le mécanicien.
"""

import uuid
from collections import defaultdict
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, text

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.authz.principal import evaluate
from app.core.errors import AppError
from app.core.http import PageParams, check_version
from app.core.logging import security_logger
from app.dispatch.contracts import mission_vehicle, suspend_running_missions
from app.fleet.contracts import VehicleFacts, change_status_for_maintenance, vehicle_facts
from app.identity.contracts import display_names, users_with_roles
from app.maintenance.models import WorkOrder, WorkOrderEvent, WorkOrderLabour
from app.maintenance.schemas import (
    EventOut,
    LabourCreate,
    LabourOut,
    MechanicOut,
    WorkOrderCreate,
    WorkOrderDecision,
    WorkOrderOut,
    WorkOrderProgress,
)
from app.organization.contracts import local_date

TERMINAL = frozenset({"CLOSED", "REJECTED", "CANCELLED"})
# OT qui retiennent le véhicule à l'atelier (pas de remise à disposition tant qu'il en reste un).
IN_WORKSHOP = frozenset({"IN_PROGRESS", "AWAITING_PARTS", "QUALITY_CHECK"})
MECHANIC_ROLES = ("MECHANIC", "WORKSHOP_CHIEF")
# Toute personne ayant agi sur l'intervention est exclue de la remise en service (RM-114).
EXECUTION_EVENTS = ("STARTED", "AWAITING_PARTS", "RESUMED", "SUBMITTED", "NOTED")
MAX_MINUTES_PER_DAY = 24 * 60
# action → (états de départ, état d'arrivée, événement, motif obligatoire)
DECISIONS: dict[str, tuple[frozenset[str], str | None, str, bool]] = {
    "APPROVE": (frozenset({"REQUESTED"}), "APPROVED", "APPROVED", False),
    "REJECT": (frozenset({"REQUESTED"}), "REJECTED", "REJECTED", True),
    # Assignation ou réassignation tant que l'intervention n'est pas terminée.
    "ASSIGN": (frozenset({"APPROVED", "ASSIGNED", "IN_PROGRESS", "AWAITING_PARTS"}), None, "ASSIGNED", False),
    "CANCEL": (frozenset({"REQUESTED", "APPROVED", "ASSIGNED"}), "CANCELLED", "CANCELLED", True),
    "QC_PASS": (frozenset({"QUALITY_CHECK"}), "CLOSED", "CLOSED", False),
    "QC_FAIL": (frozenset({"QUALITY_CHECK"}), "IN_PROGRESS", "QC_FAILED", True),
}
PROGRESS: dict[str, tuple[frozenset[str], str | None, str | None, bool]] = {
    "START": (frozenset({"ASSIGNED"}), "IN_PROGRESS", "STARTED", False),
    "AWAIT_PARTS": (frozenset({"IN_PROGRESS"}), "AWAITING_PARTS", "AWAITING_PARTS", True),
    "RESUME": (frozenset({"AWAITING_PARTS"}), "IN_PROGRESS", "RESUMED", False),
    "SUBMIT": (frozenset({"IN_PROGRESS"}), "QUALITY_CHECK", "SUBMITTED", False),
    # Mise à jour du diagnostic ou du compte rendu, sans changement d'état (tracée dans la chronologie).
    # Figé pendant le contrôle qualité (revue L3A-R-07) : le valideur examine ce qui a été soumis.
    "NOTE": (frozenset({"ASSIGNED", "IN_PROGRESS", "AWAITING_PARTS"}), None, "NOTED", False),
}


def reference(number: int) -> str:
    return f"OT-{number:06d}"


# --- Lecture -------------------------------------------------------------------------------------------


def work_orders_out(auth: Authorized, orders: list[WorkOrder], *, detail: bool = False) -> list[WorkOrderOut]:
    if not orders:
        return []
    db = auth.db
    ids = [o.work_order_id for o in orders]
    fleet = vehicle_facts(db, {o.vehicle_id for o in orders})
    minutes = dict(
        db.execute(
            select(WorkOrderLabour.work_order_id, func.sum(WorkOrderLabour.minutes))
            .where(WorkOrderLabour.work_order_id.in_(ids))
            .group_by(WorkOrderLabour.work_order_id)
        ).all()
    )
    events: dict[uuid.UUID, list[WorkOrderEvent]] = defaultdict(list)
    labour: dict[uuid.UUID, list[WorkOrderLabour]] = defaultdict(list)
    people: set[uuid.UUID] = {o.assigned_to for o in orders if o.assigned_to}
    if detail:
        for e in db.execute(
            select(WorkOrderEvent)
            .where(WorkOrderEvent.work_order_id.in_(ids))
            .order_by(WorkOrderEvent.occurred_at)
        ).scalars():
            events[e.work_order_id].append(e)
            people.add(e.actor_user_id)
            if e.subject_user_id:
                people.add(e.subject_user_id)
        for entry in db.execute(
            select(WorkOrderLabour)
            .where(WorkOrderLabour.work_order_id.in_(ids))
            .order_by(WorkOrderLabour.performed_on, WorkOrderLabour.recorded_at)
        ).scalars():
            labour[entry.work_order_id].append(entry)
            people.add(entry.mechanic_id)
    names = display_names(db, people)
    manage = evaluate(auth.principal, "maintenance.work_order.manage")
    execute = evaluate(auth.principal, "maintenance.work_order.execute")

    def named(site_id: uuid.UUID) -> bool:
        # Revue L3A-R-13 : qui a travaillé et combien de temps n'est visible que de l'atelier, de
        # l'exploitation qui décide et de l'audit — pas du dispatcher ni du HSE.
        return (
            (manage is not None and manage.covers_site(site_id))
            or (execute is not None and execute.covers_site(site_id))
            or "AUDITOR" in auth.scope.roles_for_site(site_id)
        )

    out = []
    for o in orders:
        show = named(o.site_id)
        data: dict[str, Any] = {
            "work_order_id": o.work_order_id,
            "number": o.number,
            "reference": reference(o.number),
            "site_id": o.site_id,
            "vehicle_id": o.vehicle_id,
            "vehicle_fleet_number": fleet[o.vehicle_id].fleet_number if o.vehicle_id in fleet else "?",
            "mission_id": o.mission_id,
            "kind": o.kind,
            "priority": o.priority,
            "symptom_code": o.symptom_code,
            "description": o.description,
            "immobilize": o.immobilize,
            "status": o.status,
            "status_reason": o.status_reason,
            "assigned_to": o.assigned_to if show else None,
            "assigned_name": names.get(o.assigned_to) if o.assigned_to and show else None,
            "expected_ready_at": o.expected_ready_at,
            "diagnosis": o.diagnosis,
            "work_done": o.work_done,
            "parts_note": o.parts_note,
            "reported_at": o.reported_at,
            "reported_by": o.reported_by if show else None,
            "approved_at": o.approved_at,
            "started_at": o.started_at,
            "submitted_at": o.submitted_at,
            "closed_at": o.closed_at,
            "closed_by": o.closed_by if show else None,
            "labour_minutes": int(minutes.get(o.work_order_id) or 0),
            "row_version": o.row_version,
        }
        if detail:
            data["events"] = [
                EventOut(
                    event_type=e.event_type,
                    from_status=e.from_status,
                    to_status=e.to_status,
                    reason=e.reason,
                    actor_user_id=e.actor_user_id if show else None,
                    actor_name=names.get(e.actor_user_id) if show else None,
                    subject_user_id=e.subject_user_id if show else None,
                    subject_name=names.get(e.subject_user_id) if show and e.subject_user_id else None,
                    occurred_at=e.occurred_at,
                )
                for e in events[o.work_order_id]
            ]
            # Temps passé nominatif : réservé aux mêmes rôles que les noms (revue automatique, L3A-R-13).
            data["labour"] = (
                None
                if not show
                else [
                    LabourOut(
                        work_order_labour_id=entry.work_order_labour_id,
                        mechanic_id=entry.mechanic_id,
                        mechanic_name=names.get(entry.mechanic_id) if show else None,
                        minutes=entry.minutes,
                        performed_on=entry.performed_on,
                        note=entry.note,
                        recorded_at=entry.recorded_at,
                    )
                    for entry in labour[o.work_order_id]
                ]
            )
        out.append(WorkOrderOut(**data))
    return out


def work_order_in_scope(auth: Authorized, work_order_id: uuid.UUID, *, for_update: bool = False) -> WorkOrder:
    stmt = select(WorkOrder).where(WorkOrder.work_order_id == work_order_id)
    order = auth.db.execute(stmt).scalar_one_or_none()
    if order is None or not auth.scope.covers_site(order.site_id):
        security_logger.info(
            "item_not_found", extra={"entity_type": "work_order", "entity_id": str(work_order_id)}
        )
        raise AppError("NOT_FOUND")
    if for_update:
        # Verrou APRÈS le contrôle de portée ; état relu sous verrou.
        order = auth.db.execute(
            stmt.with_for_update(key_share=True).execution_options(populate_existing=True)
        ).scalar_one()
    return order


def list_work_orders(
    auth: Authorized,
    page: PageParams,
    *,
    site_id: uuid.UUID | None,
    vehicle_id: uuid.UUID | None,
    status: str | None,
    open_only: bool,
) -> tuple[list[WorkOrder], int]:
    stmt = select(WorkOrder)
    if not auth.scope.tenant_wide:
        stmt = stmt.where(WorkOrder.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        stmt = stmt.where(WorkOrder.site_id == site_id)
    if vehicle_id is not None:
        stmt = stmt.where(WorkOrder.vehicle_id == vehicle_id)
    if status is not None:
        stmt = stmt.where(WorkOrder.status == status)
    if open_only:
        stmt = stmt.where(WorkOrder.status.not_in(TERMINAL))
    total = auth.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = auth.db.execute(
        stmt.order_by(WorkOrder.reported_at.desc(), WorkOrder.number.desc())
        .offset(page.offset)
        .limit(page.page_size)
    )
    return list(rows.scalars()), total


def mechanics(auth: Authorized, site_id: uuid.UUID) -> list[MechanicOut]:
    if not auth.scope.covers_site(site_id):
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "site_id"}])
    return [
        MechanicOut(user_account_id=user_id, display_name=name)
        for user_id, name in users_with_roles(auth.db, MECHANIC_ROLES, site_id, auth.clock.now())
    ]


# --- Écritures ----------------------------------------------------------------------------------------


def _event(
    auth: Authorized,
    order: WorkOrder,
    event_type: str,
    source: str | None,
    reason: str | None,
    subject: uuid.UUID | None = None,
) -> None:
    auth.db.add(
        WorkOrderEvent(
            tenant_id=auth.tenant_id,
            work_order_id=order.work_order_id,
            event_type=event_type,
            from_status=source,
            to_status=order.status,
            reason=reason,
            actor_user_id=auth.user_id,
            subject_user_id=subject,
            # Même horloge que les autres horodatages de l'OT (revue L3A-R-14).
            occurred_at=auth.clock.now(),
        )
    )


def _audit(auth: Authorized, action: str, order: WorkOrder, **extra: Any) -> None:
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        action=action,
        entity_type="work_order",
        entity_id=order.work_order_id,
        site_id=order.site_id,
        actor_user_id=auth.user_id,
        **extra,
    )


def _next_number(auth: Authorized) -> int:
    """Numéro suivant du tenant : incrément atomique sous verrou de ligne (pas de doublon concurrent)."""
    return int(
        auth.db.execute(
            text(
                "INSERT INTO maintenance_counter (tenant_id, last_number) VALUES (:t, 1) "
                "ON CONFLICT (tenant_id) DO UPDATE SET last_number = maintenance_counter.last_number + 1 "
                "RETURNING last_number"
            ),
            {"t": str(auth.tenant_id)},
        ).scalar_one()
    )


def _immobilize(auth: Authorized, vehicle_id: uuid.UUID) -> bool:
    """D-44 : panne bloquante → véhicule immobilisé, missions en cours suspendues (événement système)."""
    changed = change_status_for_maintenance(
        auth, vehicle_id, "IMMOBILIZED", "BREAKDOWN", "vehicle.change_status"
    )
    suspend_running_missions(auth, vehicle_id, "BREAKDOWN")
    return changed


def _locked_vehicle(auth: Authorized, order: WorkOrder) -> VehicleFacts:
    """Véhicule de l'OT, verrouillé, toujours sur le site de l'OT et dans la portée (revue L3A-R-09)."""
    facts = vehicle_facts(auth.db, [order.vehicle_id], lock=True).get(order.vehicle_id)
    if facts is None or facts.site_id != order.site_id or not auth.scope.covers_site(facts.site_id):
        raise AppError("WORK_ORDER_STATE_INVALID", details={"reason": "vehicle_moved"})
    return facts


def _release_if_free(auth: Authorized, order: WorkOrder, facts: VehicleFacts) -> bool:
    """Remise à disposition (D-44) : seulement un véhicule retenu par l'atelier — en maintenance, ou
    immobilisé pour panne — et qu'aucun autre OT ne retient. Un statut posé pour une autre raison
    (accident, interdiction HSE…) n'est jamais écrasé (revue L3A-R-05)."""
    # Une immobilisation n'est levée que si CET OT l'a posée au signalement (revue automatique) :
    # jamais celle d'une autre personne, même avec le motif « panne ».
    held_by_workshop = facts.status == "IN_MAINTENANCE" or (
        facts.status == "IMMOBILIZED"
        and facts.status_reason_code == "BREAKDOWN"
        and order.immobilized_vehicle
    )
    if not held_by_workshop or _still_in_workshop(auth, order):
        return False
    return change_status_for_maintenance(auth, order.vehicle_id, "AVAILABLE", None, "vehicle.release")


def _create_work_order_uncommitted(auth: Authorized, body: WorkOrderCreate) -> WorkOrderOut:
    """Construire l’OT, son evenement et son audit sans commit."""
    db = auth.db
    facts = vehicle_facts(db, [body.vehicle_id]).get(body.vehicle_id)
    if facts is None or not auth.scope.covers_site(facts.site_id) or facts.status == "RETIRED":
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "vehicle_id"}])
    if body.mission_id is not None and mission_vehicle(auth, body.mission_id) != (
        body.vehicle_id,
        facts.site_id,
    ):
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "mission_id"}])
    # Verrou du véhicule avant toute écriture, comme la clôture : pas de remise à disposition concurrente
    # d'un véhicule qu'on est en train d'immobiliser (revue L3A-R-02). Portée contrôlée juste avant sans
    # verrou, puis tout est revérifié sur la lecture verrouillée (revue automatique : données périmées).
    locked = vehicle_facts(db, [body.vehicle_id], lock=True).get(body.vehicle_id)
    if locked is None or locked.site_id != facts.site_id or locked.status == "RETIRED":
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "vehicle_id"}])
    immobilized = _immobilize(auth, body.vehicle_id) if body.immobilize else False
    now = auth.clock.now()
    order = WorkOrder(
        tenant_id=auth.tenant_id,
        # Numéro pris en dernier : le verrou du compteur du tenant est tenu le moins longtemps (L3A-R-10).
        number=_next_number(auth),
        site_id=facts.site_id,
        vehicle_id=body.vehicle_id,
        mission_id=body.mission_id,
        priority=body.priority,
        symptom_code=body.symptom_code,
        description=(body.description or "").strip() or None,
        immobilize=body.immobilize,
        immobilized_vehicle=immobilized,
        reported_at=now,
        reported_by=auth.user_id,
        created_by=auth.user_id,
        updated_by=auth.user_id,
    )
    db.add(order)
    db.flush()
    _event(auth, order, "REQUESTED", None, None)
    _audit(
        auth,
        "work_order.request",
        order,
        after={
            "reference": reference(order.number),
            "vehicle_id": str(order.vehicle_id),
            "symptom_code": order.symptom_code,
            "priority": order.priority,
            "immobilize": order.immobilize,
        },
    )
    db.flush()
    out = work_orders_out(auth, [order], detail=True)[0]
    return out

def create_work_order(auth: Authorized, body: WorkOrderCreate) -> WorkOrderOut:
    """US-3.01 : conserve la transaction existante pour l’API corrective."""
    out = _create_work_order_uncommitted(auth, body)
    auth.db.commit()
    return out



def _ensure_mechanic(auth: Authorized, user_id: uuid.UUID, site_id: uuid.UUID) -> None:
    """RM-112 : compte actif avec le rôle mécanicien (ou chef d'atelier) sur le site ou toute la société."""
    eligible = {u for u, _ in users_with_roles(auth.db, MECHANIC_ROLES, site_id, auth.clock.now())}
    if user_id not in eligible:
        raise AppError("MECHANIC_NOT_ELIGIBLE", details=[{"field": "assigned_to"}])


def _still_in_workshop(auth: Authorized, order: WorkOrder) -> bool:
    """Un autre OT ouvert retient-il le véhicule (à l'atelier, ou panne bloquante non traitée) ?"""
    others = auth.db.execute(
        select(func.count()).where(
            WorkOrder.vehicle_id == order.vehicle_id,
            WorkOrder.work_order_id != order.work_order_id,
            WorkOrder.status.not_in(TERMINAL),
            WorkOrder.status.in_(IN_WORKSHOP) | WorkOrder.immobilize.is_(True),
        )
    ).scalar_one()
    return bool(others)


def _executors(auth: Authorized, order: WorkOrder) -> set[uuid.UUID]:
    db = auth.db
    actors = set(
        db.execute(
            select(WorkOrderEvent.actor_user_id).where(
                WorkOrderEvent.work_order_id == order.work_order_id,
                WorkOrderEvent.event_type.in_(EXECUTION_EVENTS),
            )
        ).scalars()
    )
    for mechanic, recorder in db.execute(
        select(WorkOrderLabour.mechanic_id, WorkOrderLabour.recorded_by).where(
            WorkOrderLabour.work_order_id == order.work_order_id
        )
    ).all():
        actors |= {mechanic, recorder}
    # Assignés successifs (revue L3A-R-08).
    actors |= {
        subject
        for subject in db.execute(
            select(WorkOrderEvent.subject_user_id).where(
                WorkOrderEvent.work_order_id == order.work_order_id,
                WorkOrderEvent.subject_user_id.is_not(None),
            )
        ).scalars()
        if subject is not None
    }
    if order.assigned_to is not None:
        actors.add(order.assigned_to)
    return actors


def decide(auth: Authorized, work_order_id: uuid.UUID, body: WorkOrderDecision, version: int) -> WorkOrderOut:
    """US-3.02, 3.03, 3.05 : approbation, rejet, assignation, annulation, contrôle qualité."""
    db = auth.db
    order = work_order_in_scope(auth, work_order_id, for_update=True)
    check_version(version, order.row_version)
    allowed, target, event_type, reason_required = DECISIONS[body.action]
    source = order.status
    if source not in allowed:
        raise AppError("WORK_ORDER_STATE_INVALID", details={"status": source, "action": body.action})
    if reason_required and body.reason_code is None:
        raise AppError("STATUS_REASON_REQUIRED")
    now = auth.clock.now()
    changed: dict[str, Any] = {}
    if body.expected_ready_at is not None and body.action in ("APPROVE", "ASSIGN"):
        if body.expected_ready_at < now:
            raise AppError("VALIDATION_ERROR", details=[{"field": "expected_ready_at", "type": "in_past"}])
        order.expected_ready_at = body.expected_ready_at
        changed["expected_ready_at"] = body.expected_ready_at.isoformat()
    if body.action == "APPROVE":
        order.approved_at, order.approved_by = now, auth.user_id
    elif body.action == "ASSIGN":
        if body.assigned_to is None:
            raise AppError("VALIDATION_ERROR", details=[{"field": "assigned_to", "type": "missing"}])
        _ensure_mechanic(auth, body.assigned_to, order.site_id)
        changed["previous_assigned_to"] = str(order.assigned_to) if order.assigned_to else None
        order.assigned_to = body.assigned_to
        changed["assigned_to"] = str(body.assigned_to)
        if source == "APPROVED":
            target = "ASSIGNED"
    elif body.action == "QC_PASS":
        # RM-114 : la remise en service n'est pas validée par qui a agi sur l'intervention, même après une
        # réassignation (assigné, toute étape d'exécution ou modification du compte rendu, temps passé).
        if auth.user_id in _executors(auth, order):
            raise AppError("SELF_RELEASE_FORBIDDEN")
        order.closed_at, order.closed_by = now, auth.user_id
        changed["vehicle_released"] = _release_if_free(auth, order, _locked_vehicle(auth, order))
    elif body.action in ("REJECT", "CANCEL") and order.immobilize:
        # Revue L3A-R-04 : une panne bloquante rejetée ou annulée ne laisse pas le véhicule immobilisé
        # si rien d'autre ne le retient (fausse alerte, doublon).
        changed["vehicle_released"] = _release_if_free(auth, order, _locked_vehicle(auth, order))
    if target is not None:
        order.status = target
        # Revue L3A-R-06 : le motif ne change qu'avec l'état.
        order.status_reason = body.reason_code if order.status in ("REJECTED", "CANCELLED") else None
    order.updated_by = auth.user_id
    db.flush()
    _event(
        auth,
        order,
        event_type,
        source,
        body.reason_code,
        body.assigned_to if body.action == "ASSIGN" else None,
    )
    _audit(
        auth,
        f"work_order.{body.action.lower()}",
        order,
        reason=body.reason_code,
        before={"status": source},
        after={"status": order.status, **changed},
        changed_fields=(
            "status",
            *(k for k in changed if k not in ("previous_assigned_to", "vehicle_released")),
        ),
    )
    db.flush()
    out = work_orders_out(auth, [order], detail=True)[0]
    db.commit()
    return out


def _ensure_executor(auth: Authorized, order: WorkOrder) -> None:
    """RM-113 : le mécanicien assigné, ou un chef d'atelier sur ce site."""
    if order.assigned_to == auth.user_id or "WORKSHOP_CHIEF" in auth.scope.roles_for_site(order.site_id):
        return
    raise AppError("WORK_ORDER_NOT_ASSIGNEE")


def progress(
    auth: Authorized, work_order_id: uuid.UUID, body: WorkOrderProgress, version: int
) -> WorkOrderOut:
    """US-3.04 : intervention (début, attente de pièces, reprise, fin de travaux) et compte rendu."""
    db = auth.db
    order = work_order_in_scope(auth, work_order_id, for_update=True)
    check_version(version, order.row_version)
    _ensure_executor(auth, order)
    allowed, target, event_type, reason_required = PROGRESS[body.action]
    source = order.status
    if source not in allowed:
        raise AppError("WORK_ORDER_STATE_INVALID", details={"status": source, "action": body.action})
    if reason_required and body.reason_code is None:
        raise AppError("STATUS_REASON_REQUIRED")
    texts = {
        f: getattr(body, f) for f in ("diagnosis", "work_done", "parts_note") if getattr(body, f) is not None
    }
    for name, value in texts.items():
        setattr(order, name, value.strip() or None)
    if body.action == "SUBMIT" and not order.work_done:
        raise AppError("VALIDATION_ERROR", details=[{"field": "work_done", "type": "missing"}])
    now = auth.clock.now()
    if body.action == "START":
        order.started_at = order.started_at or now
        _locked_vehicle(auth, order)
        # D-44 : le véhicule entre à l'atelier ; une mission encore en cours est suspendue.
        change_status_for_maintenance(auth, order.vehicle_id, "IN_MAINTENANCE", None, "vehicle.change_status")
        suspend_running_missions(auth, order.vehicle_id, "BREAKDOWN")
    elif body.action == "SUBMIT":
        order.submitted_at = now
    if target is not None:
        order.status = target
        order.status_reason = body.reason_code if order.status == "AWAITING_PARTS" else None
    order.updated_by = auth.user_id
    db.flush()
    if event_type is not None:
        _event(auth, order, event_type, source, body.reason_code)
    _audit(
        auth,
        f"work_order.{body.action.lower()}",
        order,
        reason=body.reason_code,
        before={"status": source},
        after={"status": order.status},
        changed_fields=("status", *texts),
    )
    db.flush()
    out = work_orders_out(auth, [order], detail=True)[0]
    db.commit()
    return out


def add_labour(auth: Authorized, work_order_id: uuid.UUID, body: LabourCreate) -> WorkOrderOut:
    """RM-115 : temps passé, ajout seul, sur un OT en cours d'intervention."""
    db = auth.db
    order = work_order_in_scope(auth, work_order_id, for_update=True)
    _ensure_executor(auth, order)
    if order.status not in ("ASSIGNED", *IN_WORKSHOP):
        raise AppError("WORK_ORDER_STATE_INVALID", details={"status": order.status, "action": "LABOUR"})
    mechanic = body.mechanic_id or auth.user_id
    if mechanic != auth.user_id and "WORKSHOP_CHIEF" not in auth.scope.roles_for_site(order.site_id):
        raise AppError("WORK_ORDER_NOT_ASSIGNEE")  # seul le chef d'atelier saisit pour un autre
    _ensure_mechanic(auth, mechanic, order.site_id)
    today = local_date(db, order.site_id, auth.clock.now())
    reported = local_date(db, order.site_id, order.reported_at)
    if body.performed_on > today or body.performed_on < reported - timedelta(days=1):
        raise AppError("VALIDATION_ERROR", details=[{"field": "performed_on", "type": "out_of_range"}])
    # Sérialise les saisies d'un même mécanicien pour un même jour : le plafond ne peut pas être dépassé
    # par deux saisies concurrentes (revue automatique).
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"{auth.tenant_id}/{mechanic}/{body.performed_on.isoformat()}/labour"},
    )
    already = db.execute(
        select(func.coalesce(func.sum(WorkOrderLabour.minutes), 0)).where(
            WorkOrderLabour.mechanic_id == mechanic, WorkOrderLabour.performed_on == body.performed_on
        )
    ).scalar_one()
    if already + body.minutes > MAX_MINUTES_PER_DAY:
        # Revue L3A-R-11 : jamais plus de 24 h par mécanicien et par jour, tous OT confondus.
        raise AppError("VALIDATION_ERROR", details=[{"field": "minutes", "type": "daily_limit"}])
    entry = WorkOrderLabour(
        tenant_id=auth.tenant_id,
        work_order_id=order.work_order_id,
        mechanic_id=mechanic,
        minutes=body.minutes,
        performed_on=body.performed_on,
        note=body.note.strip() if body.note else None,
        recorded_by=auth.user_id,
    )
    db.add(entry)
    db.flush()
    _audit(
        auth,
        "work_order.labour",
        order,
        after={
            "mechanic_id": str(mechanic),
            "minutes": body.minutes,
            "performed_on": body.performed_on.isoformat(),
        },
    )
    out = work_orders_out(auth, [order], detail=True)[0]
    db.commit()
    return out
