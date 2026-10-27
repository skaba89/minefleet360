import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import AwareDatetime

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.http import IfMatch, Page, Pagination, etag
from app.dispatch import service, weighing
from app.dispatch.models import Material, SiteLocation
from app.dispatch.schemas import (
    IndicatorsOut,
    LocationCreate,
    LocationOut,
    LocationUpdate,
    MaterialCreate,
    MaterialOut,
    MaterialUpdate,
    MissionCreate,
    MissionEventCreate,
    MissionOut,
    MissionStatus,
    WeighingCorrection,
    WeighingCreate,
    WeighingOut,
    WeighingStatus,
    WeighingVoid,
)

router = APIRouter(tags=["dispatch"], route_class=SecuredRoute)

LocationRead = Annotated[Authorized, Depends(Require("dispatch.location.read"))]
LocationManage = Annotated[Authorized, Depends(Require("dispatch.location.manage"))]
MaterialRead = Annotated[Authorized, Depends(Require("dispatch.material.read"))]
MaterialManage = Annotated[Authorized, Depends(Require("dispatch.material.manage"))]
MissionRead = Annotated[Authorized, Depends(Require("dispatch.mission.read"))]


def _location(location: SiteLocation, response: Response | None = None) -> LocationOut:
    if response is not None:
        response.headers["ETag"] = etag(location.row_version)
    return LocationOut.model_validate(location, from_attributes=True)


def _material(material: Material, response: Response | None = None) -> MaterialOut:
    if response is not None:
        response.headers["ETag"] = etag(material.row_version)
    return MaterialOut.model_validate(material, from_attributes=True)


@router.get("/site-locations", response_model=list[LocationOut])
def list_locations(
    auth: LocationRead, site_id: uuid.UUID | None = None, include_inactive: bool = False
) -> list[LocationOut]:
    return [
        _location(loc)
        for loc in service.list_locations(auth, site_id=site_id, include_inactive=include_inactive)
    ]


@router.post("/site-locations", status_code=status.HTTP_201_CREATED, response_model=LocationOut)
def create_location(body: LocationCreate, auth: LocationManage, response: Response) -> LocationOut:
    return _location(service.create_location(auth, body), response)


@router.patch("/site-locations/{site_location_id}", response_model=LocationOut)
def update_location(
    site_location_id: uuid.UUID,
    body: LocationUpdate,
    auth: LocationManage,
    version: IfMatch,
    response: Response,
) -> LocationOut:
    return _location(service.update_location(auth, site_location_id, body, version), response)


@router.get("/materials", response_model=list[MaterialOut])
def list_materials(auth: MaterialRead, include_inactive: bool = False) -> list[MaterialOut]:
    return [_material(m) for m in service.list_materials(auth, include_inactive=include_inactive)]


@router.post("/materials", status_code=status.HTTP_201_CREATED, response_model=MaterialOut)
def create_material(body: MaterialCreate, auth: MaterialManage, response: Response) -> MaterialOut:
    return _material(service.create_material(auth, body), response)


@router.patch("/materials/{material_id}", response_model=MaterialOut)
def update_material(
    material_id: uuid.UUID, body: MaterialUpdate, auth: MaterialManage, version: IfMatch, response: Response
) -> MaterialOut:
    return _material(service.update_material(auth, material_id, body, version), response)


@router.get("/missions", response_model=Page[MissionOut], response_model_exclude_unset=True)
def list_missions(
    auth: MissionRead,
    page: Pagination,
    site_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    status_filter: Annotated[MissionStatus | None, Query(alias="status")] = None,
    open_only: bool = False,
) -> Page[MissionOut]:
    items, total = service.list_missions(
        auth, page, site_id=site_id, status=status_filter, vehicle_id=vehicle_id, open_only=open_only
    )
    return Page(
        items=service.missions_out(auth, items), page=page.page, page_size=page.page_size, total=total
    )


@router.get("/missions/{mission_id}", response_model=MissionOut, response_model_exclude_unset=True)
def get_mission(mission_id: uuid.UUID, auth: MissionRead, response: Response) -> MissionOut:
    out = service.missions_out(auth, [service.mission_in_scope(auth, mission_id)], detail=True)[0]
    response.headers["ETag"] = etag(out.row_version)
    return out


@router.post(
    "/missions",
    status_code=status.HTTP_201_CREATED,
    response_model=MissionOut,
    response_model_exclude_unset=True,
)
def create_mission(
    body: MissionCreate,
    auth: Annotated[Authorized, Depends(Require("dispatch.mission.create"))],
    response: Response,
) -> MissionOut:
    out = service.create_mission(auth, body)
    response.headers["ETag"] = etag(out.row_version)
    return out


@router.post("/missions/{mission_id}/events", response_model=MissionOut, response_model_exclude_unset=True)
def record_event(
    mission_id: uuid.UUID,
    body: MissionEventCreate,
    auth: Annotated[Authorized, Depends(Require("dispatch.mission.progress"))],
    version: IfMatch,
    response: Response,
) -> MissionOut:
    out = service.record_event(auth, mission_id, body, version)
    response.headers["ETag"] = etag(out.row_version)
    return out


# --- Pesées et indicateurs (lot 2b) ---------------------------------------------------------------------

WeighingRead = Annotated[Authorized, Depends(Require("dispatch.weighing.read"))]
WeighingCorrect = Annotated[Authorized, Depends(Require("dispatch.weighing.correct"))]


@router.get("/weighing-tickets", response_model=Page[WeighingOut])
def list_weighing_tickets(
    auth: WeighingRead,
    page: Pagination,
    site_id: uuid.UUID | None = None,
    mission_id: uuid.UUID | None = None,
    status_filter: Annotated[WeighingStatus | None, Query(alias="status")] = None,
    overload: bool | None = None,
    period_start: AwareDatetime | None = None,
    period_end: AwareDatetime | None = None,
) -> Page[WeighingOut]:
    items, total = weighing.list_tickets(
        auth,
        page,
        site_id=site_id,
        mission_id=mission_id,
        status=status_filter,
        overload=overload,
        period_start=period_start,
        period_end=period_end,
    )
    return Page(
        items=weighing.tickets_out(auth, items), page=page.page, page_size=page.page_size, total=total
    )


@router.get("/weighing-tickets/{weighing_ticket_id}", response_model=WeighingOut)
def get_weighing_ticket(weighing_ticket_id: uuid.UUID, auth: WeighingRead) -> WeighingOut:
    return weighing.tickets_out(auth, [weighing.ticket_in_scope(auth, weighing_ticket_id)])[0]


@router.post("/weighing-tickets", status_code=status.HTTP_201_CREATED, response_model=WeighingOut)
def record_weighing_ticket(
    body: WeighingCreate,
    auth: Annotated[Authorized, Depends(Require("dispatch.weighing.record"))],
    response: Response,
) -> WeighingOut:
    out, created = weighing.record_ticket(auth, body)
    if not created:
        response.status_code = status.HTTP_200_OK  # renvoi identique (RM-074)
    return out


@router.post("/weighing-tickets/{weighing_ticket_id}/approve", response_model=WeighingOut)
def approve_weighing_ticket(
    weighing_ticket_id: uuid.UUID,
    auth: Annotated[Authorized, Depends(Require("dispatch.weighing.approve"))],
) -> WeighingOut:
    return weighing.approve(auth, weighing_ticket_id)


@router.post("/weighing-tickets/{weighing_ticket_id}/void", response_model=WeighingOut)
def void_weighing_ticket(
    weighing_ticket_id: uuid.UUID, body: WeighingVoid, auth: WeighingCorrect
) -> WeighingOut:
    return weighing.void(auth, weighing_ticket_id, body.reason_code)


@router.post(
    "/weighing-tickets/{weighing_ticket_id}/correct",
    status_code=status.HTTP_201_CREATED,
    response_model=WeighingOut,
)
def correct_weighing_ticket(
    weighing_ticket_id: uuid.UUID, body: WeighingCorrection, auth: WeighingCorrect
) -> WeighingOut:
    return weighing.correct(auth, weighing_ticket_id, body)


@router.get("/dispatch-indicators", response_model=IndicatorsOut)
def dispatch_indicators(
    auth: Annotated[Authorized, Depends(Require("dispatch.indicators.read"))],
    site_id: uuid.UUID | None = None,
    period_start: AwareDatetime | None = None,
    period_end: AwareDatetime | None = None,
) -> IndicatorsOut:
    return weighing.indicators(auth, site_id=site_id, period_start=period_start, period_end=period_end)
