"""Lecture du journal d'audit (US-1.26) : tenant courant uniquement, aucune route d'écriture."""

import logging
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.audit.models import AuditEvent
from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.errors import AppError
from app.core.http import Page, Pagination

router = APIRouter(prefix="/audit-events", tags=["audit"], route_class=SecuredRoute)
logger = logging.getLogger("minefleet.audit.read")


class AuditEventOut(BaseModel):
    audit_event_id: uuid.UUID
    occurred_at: datetime
    site_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    actor_kind: str
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    outcome: str
    reason: str | None
    changed_fields: list[str] | None
    before_data: dict[str, Any] | None
    after_data: dict[str, Any] | None
    request_id: uuid.UUID | None


AuditRead = Annotated[Authorized, Depends(Require("audit.event.read"))]


@router.get("", response_model=Page[AuditEventOut])
def list_events(
    auth: AuditRead,
    page: Pagination,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    actor_user_id: uuid.UUID | None = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    entity_type: Annotated[str | None, Query(max_length=60)] = None,
    entity_id: uuid.UUID | None = None,
    site_id: uuid.UUID | None = None,
) -> Page[AuditEventOut]:
    for value in (occurred_from, occurred_to):
        if value is not None and value.tzinfo is None:
            raise AppError(
                "VALIDATION_ERROR", details=[{"field": "occurred_from/occurred_to", "type": "timezone"}]
            )
    stmt = select(AuditEvent)
    filters: dict[Any, Any] = {
        AuditEvent.actor_user_id: actor_user_id,
        AuditEvent.action: action,
        AuditEvent.entity_type: entity_type,
        AuditEvent.entity_id: entity_id,
        AuditEvent.site_id: site_id,
    }
    for column, value in filters.items():
        if value is not None:
            stmt = stmt.where(column == value)
    if occurred_from is not None:
        stmt = stmt.where(AuditEvent.occurred_at >= occurred_from)
    if occurred_to is not None:
        stmt = stmt.where(AuditEvent.occurred_at < occurred_to)
    total = auth.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = auth.db.execute(
        stmt.order_by(AuditEvent.occurred_at.desc(), AuditEvent.audit_seq.desc())
        .offset(page.offset)
        .limit(page.page_size)
    ).scalars()
    # Consultation tracée en log technique, pas en audit (US-1.26 A8).
    logger.info("audit_read", extra={"user_id": str(auth.user_id), "tenant_id": str(auth.tenant_id)})
    return Page(
        items=[AuditEventOut.model_validate(r, from_attributes=True) for r in rows],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.get("/{event_id}", response_model=AuditEventOut)
def get_event(event_id: uuid.UUID, auth: AuditRead) -> AuditEventOut:
    event = auth.db.execute(
        select(AuditEvent).where(AuditEvent.audit_event_id == event_id)
    ).scalar_one_or_none()
    if event is None:
        raise AppError("NOT_FOUND")
    return AuditEventOut.model_validate(event, from_attributes=True)
