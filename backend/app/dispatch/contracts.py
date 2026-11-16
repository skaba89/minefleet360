"""Contrat public du module dispatch (utilisé par la maintenance, lot 3)."""

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.dispatch.models import Mission, MissionEvent, Rotation, WeighingTicket
from app.dispatch.service import RUNNING
from app.dispatch.weighing import APPROVED, VOIDED


@dataclass(frozen=True)
class MeasuredLoad:
    """Chargement d'une rotation terminée : tonnage MESURÉ seulement si `valid` (RM-071)."""

    unloaded_at: datetime
    net_kg: int
    valid: bool  # pont-bascule, ou saisie dégradée approuvée ; sinon en attente d'approbation


def measured_loads(
    db: Session, vehicle_ids: Iterable[uuid.UUID], start: datetime, end: datetime
) -> dict[uuid.UUID, list[MeasuredLoad]]:
    """Pesées non annulées des rotations TERMINÉES déchargées dans [start, end), par engin (RLS).

    Même définition que les indicateurs dispatch : jamais de tonnage estimé (capacité nominale) ni GPS.
    """
    ids = list(set(vehicle_ids))
    out: dict[uuid.UUID, list[MeasuredLoad]] = defaultdict(list)
    if not ids:
        return out
    rows = db.execute(
        select(
            Rotation.vehicle_id,
            Rotation.unloaded_at,
            WeighingTicket.net_kg,
            or_(WeighingTicket.source == "WEIGHBRIDGE", APPROVED).label("valid"),
        )
        .join(WeighingTicket, WeighingTicket.rotation_id == Rotation.rotation_id)
        .where(
            ~VOIDED,
            Rotation.vehicle_id.in_(ids),
            Rotation.status == "COMPLETED",
            Rotation.unloaded_at >= start,
            Rotation.unloaded_at < end,
        )
        .order_by(Rotation.unloaded_at)
    ).all()
    for vehicle_id, unloaded_at, net_kg, valid in rows:
        out[vehicle_id].append(MeasuredLoad(unloaded_at, int(net_kg), bool(valid)))
    return out


def mission_vehicle(auth: Authorized, mission_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID] | None:
    """(véhicule, site) d'une mission du tenant courant (RLS), ou None."""
    row = auth.db.execute(
        select(Mission.vehicle_id, Mission.site_id).where(Mission.mission_id == mission_id)
    ).one_or_none()
    return (row[0], row[1]) if row is not None else None


def suspend_running_missions(auth: Authorized, vehicle_id: uuid.UUID, reason: str) -> list[uuid.UUID]:
    """Panne ou entrée atelier : les missions EN COURS du véhicule sont suspendues (événement système).

    Dans la transaction de l'appelant (pas de commit). La rotation ouverte reste ouverte : le dispatcher
    reprend ou réaffecte la mission (US-2.03).
    """
    db = auth.db
    missions = list(
        db.execute(
            select(Mission)
            .where(Mission.vehicle_id == vehicle_id, Mission.status.in_(RUNNING))
            .with_for_update()
        ).scalars()
    )
    now = auth.clock.now()
    for mission in missions:
        source = mission.status
        mission.status_before_suspension, mission.status, mission.status_reason = source, "SUSPENDED", reason
        mission.updated_by = auth.user_id
        db.flush()
        db.add(
            MissionEvent(
                tenant_id=auth.tenant_id,
                mission_id=mission.mission_id,
                vehicle_assignment_id=mission.vehicle_assignment_id,
                event_type="SUSPENDED",
                from_status=source,
                to_status="SUSPENDED",
                occurred_at=now,
                source="SYSTEM",
                actor_user_id=auth.user_id,
                reason=reason,
            )
        )
        record(
            db,
            tenant_id=auth.tenant_id,
            action="mission.suspended",
            entity_type="mission",
            entity_id=mission.mission_id,
            site_id=mission.site_id,
            actor_user_id=auth.user_id,
            reason=reason,
            before={"status": source},
            after={"status": "SUSPENDED", "source": "SYSTEM"},
            changed_fields=("status",),
        )
    db.flush()
    return [m.mission_id for m in missions]
