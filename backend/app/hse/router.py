import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.errors import AppError
from app.core.http import IfMatch, Page, Pagination, etag
from app.core.idempotency import claim, optional_idempotency_key
from app.hse import service
from app.hse.schemas import (
    ActionComplete,
    ActionCreate,
    ActionDecisionIn,
    ActionOut,
    ActionOwnerOut,
    ActionStatus,
    Category,
    HseSummaryOut,
    IncidentCreate,
    IncidentOut,
    IncidentStatus,
    IncidentTransition,
    Severity,
)

router = APIRouter(tags=["hse"], route_class=SecuredRoute)

IncidentRead = Annotated[Authorized, Depends(Require("hse.incident.read"))]
IncidentManage = Annotated[Authorized, Depends(Require("hse.incident.manage"))]


def _tagged[T: (IncidentOut, ActionOut)](out: T, response: Response) -> T:
    response.headers["ETag"] = etag(out.row_version)
    return out


@router.get("/hse/incidents", response_model=Page[IncidentOut], response_model_exclude_unset=True)
def list_incidents(
    auth: IncidentRead,
    page: Pagination,
    site_id: uuid.UUID | None = None,
    status_filter: Annotated[IncidentStatus | None, Query(alias="status")] = None,
    severity: Severity | None = None,
    category: Category | None = None,
    open_only: bool = False,
) -> Page[IncidentOut]:
    items, total = service.list_incidents(
        auth,
        page,
        site_id=site_id,
        status=status_filter,
        severity=severity,
        category=category,
        open_only=open_only,
    )
    return Page(
        items=service.incidents_out(auth, items), page=page.page, page_size=page.page_size, total=total
    )


@router.get("/hse/summary", response_model=HseSummaryOut)
def hse_summary(
    auth: IncidentRead,
    site_id: uuid.UUID | None = None,
    days: Annotated[int, Query(ge=1, le=366)] = 90,
) -> HseSummaryOut:
    return service.summary(auth, site_id=site_id, days=days)


@router.get("/hse/incidents/{hse_incident_id}", response_model=IncidentOut, response_model_exclude_unset=True)
def get_incident(hse_incident_id: uuid.UUID, auth: IncidentRead, response: Response) -> IncidentOut:
    incident = service.incident_in_scope(auth, hse_incident_id)
    return _tagged(service.incidents_out(auth, [incident], detail=True)[0], response)


@router.post(
    "/hse/incidents",
    status_code=status.HTTP_201_CREATED,
    response_model=IncidentOut,
    response_model_exclude_unset=True,
)
def report_incident(
    body: IncidentCreate,
    auth: Annotated[Authorized, Depends(Require("hse.incident.report"))],
    response: Response,
    idempotency_key: Annotated[str | None, Depends(optional_idempotency_key)],
) -> IncidentOut:
    if idempotency_key is None:
        return _tagged(service.report_incident(auth, body), response)
    # Déclaration rejouée depuis l'outbox terrain : la clé est liée au tenant ET au compte authentifié,
    # l'autorisation et le site sont revérifiés à chaque envoi (Require + service), le corps est empreinté.
    payload = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode("utf-8")
    owned = claim(
        auth.db,
        tenant_id=auth.tenant_id,
        user_account_id=auth.user_id,
        key=idempotency_key,
        method="POST",
        path="/hse/incidents",
        body=payload,
        now=auth.clock.now(),
    )
    if owned.replay is not None:
        if owned.replay.resource_type != "hse_incident":
            raise AppError("IDEMPOTENCY_KEY_REUSED")
        incident = service.incident_in_scope(auth, owned.replay.resource_id)
        response.headers["Idempotency-Replayed"] = "true"
        return _tagged(service.incidents_out(auth, [incident], detail=True)[0], response)
    return _tagged(service.report_incident(auth, body, idempotency_claim=owned), response)


@router.post(
    "/hse/incidents/{hse_incident_id}/transition",
    response_model=IncidentOut,
    response_model_exclude_unset=True,
)
def transition_incident(
    hse_incident_id: uuid.UUID,
    body: IncidentTransition,
    auth: IncidentManage,
    version: IfMatch,
    response: Response,
) -> IncidentOut:
    return _tagged(service.transition(auth, hse_incident_id, body, version), response)


@router.get("/hse/incidents/{hse_incident_id}/action-owners", response_model=list[ActionOwnerOut])
def list_action_owners(hse_incident_id: uuid.UUID, auth: IncidentManage) -> list[ActionOwnerOut]:
    return service.action_owners(auth, hse_incident_id)


@router.post(
    "/hse/incidents/{hse_incident_id}/actions", status_code=status.HTTP_201_CREATED, response_model=ActionOut
)
def add_action(
    hse_incident_id: uuid.UUID, body: ActionCreate, auth: IncidentManage, response: Response
) -> ActionOut:
    return _tagged(service.add_action(auth, hse_incident_id, body), response)


@router.get("/hse/corrective-actions", response_model=Page[ActionOut])
def list_actions(
    auth: IncidentRead,
    page: Pagination,
    site_id: uuid.UUID | None = None,
    status_filter: Annotated[ActionStatus | None, Query(alias="status")] = None,
    mine: bool = False,
    open_only: bool = False,
) -> Page[ActionOut]:
    items, total = service.list_actions(
        auth, page, site_id=site_id, status=status_filter, mine=mine, open_only=open_only
    )
    return Page(items=items, page=page.page, page_size=page.page_size, total=total)


@router.post("/hse/corrective-actions/{hse_corrective_action_id}/complete", response_model=ActionOut)
def complete_action(
    hse_corrective_action_id: uuid.UUID,
    body: ActionComplete,
    auth: Annotated[Authorized, Depends(Require("hse.action.complete"))],
    version: IfMatch,
    response: Response,
) -> ActionOut:
    return _tagged(service.complete_action(auth, hse_corrective_action_id, body, version), response)


@router.post("/hse/corrective-actions/{hse_corrective_action_id}/decision", response_model=ActionOut)
def decide_action(
    hse_corrective_action_id: uuid.UUID,
    body: ActionDecisionIn,
    auth: IncidentManage,
    version: IfMatch,
    response: Response,
) -> ActionOut:
    return _tagged(service.decide_action(auth, hse_corrective_action_id, body, version), response)
