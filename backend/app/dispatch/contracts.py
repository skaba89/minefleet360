"""Contrat public du module dispatch (utilisé par la maintenance, lot 3)."""

import uuid

from sqlalchemy import select

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.dispatch.models import Mission, MissionEvent
from app.dispatch.service import RUNNING


def mission_vehicle(auth: Authorized, mission_id: uuid.UUID) -> uuid.UUID | None:
    """Véhicule d'une mission du tenant courant (RLS), ou None."""
    return auth.db.execute(
        select(Mission.vehicle_id).where(Mission.mission_id == mission_id)
    ).scalar_one_or_none()


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
