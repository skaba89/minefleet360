"""Diffusion SSE de snapshots GPS sous autorisation renouvelée à chaque lecture.

Pas de broker dans cette première tranche : lecture indexée toutes les 3 s par
connexion, plafonnée à 60 s. Une PR ultérieure mesurera un bus de publication.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.authz.dependencies import Authorized, Require, load_grants
from app.authz.principal import Principal, evaluate
from app.authz.routing import SecuredRoute
from app.core.clock import Clock
from app.core.db import new_session
from app.core.errors import AppError
from app.core.tenancy import set_tenant_context
from app.fleet.gps_latest_read import latest_visible_positions
from app.fleet.gps_schemas import GpsLatestPositionOut
from app.fleet.gps_source_read import active_sources
from app.identity.models import AuthSession, UserAccount
from app.organization.models import Tenant

router = APIRouter(tags=["géolocalisation"], route_class=SecuredRoute)
GpsReader = Annotated[Authorized, Depends(Require("fleet.vehicle.read"))]
INTERVAL_SECONDS = 3
MAX_TICKS = 20


def _authorized_snapshot(principal: Principal, clock: Clock, site_id: uuid.UUID | None) -> str | None:
    """Retourne un JSON complet ou None quand la session, société ou permission a changé."""
    with new_session() as db:
        set_tenant_context(db, principal.tenant_id)
        now = clock.now()
        session = db.execute(
            select(UserAccount.mfa_enabled, AuthSession.amr)
            .join(
                UserAccount,
                (UserAccount.user_account_id == AuthSession.user_account_id)
                & (UserAccount.tenant_id == AuthSession.tenant_id),
            )
            .join(Tenant, Tenant.tenant_id == AuthSession.tenant_id)
            .where(
                AuthSession.tenant_id == principal.tenant_id,
                AuthSession.user_account_id == principal.user_id,
                AuthSession.auth_session_id == principal.session_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
                UserAccount.status == "ACTIVE",
                Tenant.status == "ACTIVE",
            )
        ).first()
        if session is None or (session.mfa_enabled and "otp" not in session.amr):
            return None
        grants = load_grants(db, principal.user_id, clock)
        current = replace(principal, grants=grants)
        scope = evaluate(current, "fleet.vehicle.read")
        if scope is None or current.mfa_enrollment_pending:
            return None
        if site_id is not None and not scope.covers_site(site_id):
            return None
        auth = Authorized(current, scope, db, clock)
        positions = latest_visible_positions(auth, as_of=now, site_id=str(site_id) if site_id else None)
        active = active_sources(auth, positions)
        payload = [
            GpsLatestPositionOut.model_validate(p)
            .model_copy(update={"source_active": p.gps_position_id in active})
            .model_dump(mode="json")
            for p in positions
        ]
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _sse(event: str, payload: str) -> str:
    """Une trame conforme SSE, sans champs sensibles dans l'id ou les commentaires."""
    return f"event: {event}\ndata: {payload}\n\n"


async def _events(
    request: Request,
    principal: Principal,
    clock: Clock,
    site_id: uuid.UUID | None,
) -> AsyncIterator[str]:
    previous: str | None = None
    for tick in range(MAX_TICKS):
        if await request.is_disconnected():
            return
        try:
            snapshot = await run_in_threadpool(_authorized_snapshot, principal, clock, site_id)
        except Exception:  # noqa: BLE001 — protocole streaming déjà démarré
            # En-têtes déjà envoyés : ne jamais transmettre d'erreur SQL ou de détail interne.
            yield _sse("unavailable", "{}")
            return
        if snapshot is None:
            yield _sse("session-ended", "{}")
            return
        if snapshot != previous:
            yield _sse("snapshot", snapshot)
            previous = snapshot
        else:
            yield ": heartbeat\n\n"
        if tick < MAX_TICKS - 1:
            await asyncio.sleep(INTERVAL_SECONDS)


@router.get("/vehicles/gps/stream", include_in_schema=False)
async def gps_stream(
    request: Request,
    auth: GpsReader,
    site_id: uuid.UUID | None = None,
) -> StreamingResponse:
    """Flux de snapshots ; jeton Bearer transmis seulement par en-tête HTTP.

    La vérification 401/403 est effectuée avant la réponse streaming. Pendant
    le flux, la session et les droits sont revalidés par une session SQL courte.
    """
    if site_id is not None and not auth.scope.covers_site(site_id):
        raise AppError("NOT_FOUND")
    principal, clock = auth.principal, auth.clock
    # Ne pas immobiliser la transaction SQL d'authentification pendant le stream.
    auth.db.rollback()
    auth.db.close()
    return StreamingResponse(
        _events(request, principal, clock, site_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
