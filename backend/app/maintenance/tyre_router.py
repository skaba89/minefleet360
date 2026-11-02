import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.http import IfMatch, Page, Pagination, etag
from app.maintenance import tyre_service as service
from app.maintenance.tyre_service import (
    TyreCreate,
    TyreDismount,
    TyreInspection,
    TyreMount,
    TyreOut,
    TyreRepair,
    TyreScrap,
    TyreStatus,
)

router = APIRouter(tags=["maintenance"], route_class=SecuredRoute)

Read = Annotated[Authorized, Depends(Require("maintenance.tyre.read"))]
Manage = Annotated[Authorized, Depends(Require("maintenance.tyre.manage"))]
Fit = Annotated[Authorized, Depends(Require("maintenance.tyre.fit"))]


def _tagged(out: TyreOut, response: Response) -> TyreOut:
    response.headers["ETag"] = etag(out.row_version)
    return out


@router.get("/tyres", response_model=Page[TyreOut], response_model_exclude_unset=True)
def list_tyres(
    auth: Read,
    page: Pagination,
    site_id: uuid.UUID | None = None,
    status_filter: Annotated[TyreStatus | None, Query(alias="status")] = None,
    vehicle_id: uuid.UUID | None = None,
    alert_only: bool = False,
) -> Page[TyreOut]:
    items, total = service.list_tyres(
        auth, page, site_id=site_id, status=status_filter, vehicle_id=vehicle_id, alert_only=alert_only
    )
    return Page(items=items, page=page.page, page_size=page.page_size, total=total)


@router.get("/tyres/{tyre_id}", response_model=TyreOut, response_model_exclude_unset=True)
def get_tyre(tyre_id: uuid.UUID, auth: Read, response: Response) -> TyreOut:
    tyre = service.tyre_in_scope(auth, tyre_id)
    return _tagged(service.tyres_out(auth, [tyre], detail=True)[0], response)


@router.post(
    "/tyres", status_code=status.HTTP_201_CREATED, response_model=TyreOut, response_model_exclude_unset=True
)
def create_tyre(body: TyreCreate, auth: Manage, response: Response) -> TyreOut:
    return _tagged(service.create_tyre(auth, body), response)


@router.post("/tyres/{tyre_id}/mount", response_model=TyreOut, response_model_exclude_unset=True)
def mount_tyre(
    tyre_id: uuid.UUID, body: TyreMount, auth: Fit, version: IfMatch, response: Response
) -> TyreOut:
    return _tagged(service.mount(auth, tyre_id, body, version), response)


@router.post("/tyres/{tyre_id}/dismount", response_model=TyreOut, response_model_exclude_unset=True)
def dismount_tyre(
    tyre_id: uuid.UUID, body: TyreDismount, auth: Fit, version: IfMatch, response: Response
) -> TyreOut:
    return _tagged(service.dismount(auth, tyre_id, body, version), response)


@router.post("/tyres/{tyre_id}/inspections", response_model=TyreOut, response_model_exclude_unset=True)
def inspect_tyre(
    tyre_id: uuid.UUID, body: TyreInspection, auth: Fit, version: IfMatch, response: Response
) -> TyreOut:
    return _tagged(service.inspect(auth, tyre_id, body, version), response)


@router.post("/tyres/{tyre_id}/repair", response_model=TyreOut, response_model_exclude_unset=True)
def repair_tyre(
    tyre_id: uuid.UUID, body: TyreRepair, auth: Manage, version: IfMatch, response: Response
) -> TyreOut:
    return _tagged(service.repair(auth, tyre_id, body, version), response)


@router.post("/tyres/{tyre_id}/scrap", response_model=TyreOut, response_model_exclude_unset=True)
def scrap_tyre(
    tyre_id: uuid.UUID, body: TyreScrap, auth: Manage, version: IfMatch, response: Response
) -> TyreOut:
    return _tagged(service.scrap(auth, tyre_id, body, version), response)
