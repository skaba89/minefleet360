import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.http import IfMatch, Page, Pagination, etag
from app.fleet import service
from app.fleet.models import Vehicle
from app.fleet.schemas import (
    StatusHistoryOut,
    VehicleCategoryOut,
    VehicleCreate,
    VehicleOut,
    VehicleRetire,
    VehicleStatus,
    VehicleStatusChange,
    VehicleUpdate,
)

router = APIRouter(tags=["flotte"], route_class=SecuredRoute)


def _out(vehicle: Vehicle, response: Response | None = None) -> VehicleOut:
    if response is not None:
        response.headers["ETag"] = etag(vehicle.row_version)
    return VehicleOut.model_validate(vehicle, from_attributes=True)


@router.get("/vehicle-categories", response_model=list[VehicleCategoryOut])
def list_categories(
    auth: Annotated[Authorized, Depends(Require("fleet.vehicle_category.read"))],
) -> list[VehicleCategoryOut]:
    return service.list_categories(auth)


@router.get("/vehicle-categories/{category_id}", response_model=VehicleCategoryOut)
def get_category(
    category_id: uuid.UUID, auth: Annotated[Authorized, Depends(Require("fleet.vehicle_category.read"))]
) -> VehicleCategoryOut:
    return service.get_category(auth, category_id)


@router.get("/vehicles", response_model=Page[VehicleOut])
def list_vehicles(
    auth: Annotated[Authorized, Depends(Require("fleet.vehicle.read"))],
    page: Pagination,
    site_id: uuid.UUID | None = None,
    vehicle_category_id: uuid.UUID | None = None,
    status_filter: Annotated[VehicleStatus | None, Query(alias="status")] = None,
    registration_number: Annotated[str | None, Query(max_length=20)] = None,
    fleet_number: Annotated[str | None, Query(max_length=30)] = None,
    include_retired: bool = False,
) -> Page[VehicleOut]:
    items, total = service.list_vehicles(
        auth,
        page,
        site_id=site_id,
        category_id=vehicle_category_id,
        status=status_filter,
        registration=registration_number,
        fleet_number=fleet_number,
        include_retired=include_retired,
    )
    return Page(items=[_out(v) for v in items], page=page.page, page_size=page.page_size, total=total)


@router.get("/vehicles/{vehicle_id}", response_model=VehicleOut)
def get_vehicle(
    vehicle_id: uuid.UUID,
    auth: Annotated[Authorized, Depends(Require("fleet.vehicle.read"))],
    response: Response,
) -> VehicleOut:
    return _out(service.get_vehicle(auth, vehicle_id), response)


@router.get("/vehicles/{vehicle_id}/status-history", response_model=list[StatusHistoryOut])
def vehicle_status_history(
    vehicle_id: uuid.UUID, auth: Annotated[Authorized, Depends(Require("fleet.vehicle.read"))]
) -> list[StatusHistoryOut]:
    return [
        StatusHistoryOut.model_validate(h, from_attributes=True)
        for h in service.status_history(auth, vehicle_id)
    ]


@router.post("/vehicles", status_code=status.HTTP_201_CREATED, response_model=VehicleOut)
def create_vehicle(
    body: VehicleCreate,
    auth: Annotated[Authorized, Depends(Require("fleet.vehicle.create"))],
    response: Response,
) -> VehicleOut:
    return _out(service.create_vehicle(auth, body), response)


@router.patch("/vehicles/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(
    vehicle_id: uuid.UUID,
    body: VehicleUpdate,
    auth: Annotated[Authorized, Depends(Require("fleet.vehicle.update"))],
    version: IfMatch,
    response: Response,
) -> VehicleOut:
    return _out(service.update_vehicle(auth, vehicle_id, body, version), response)


@router.post("/vehicles/{vehicle_id}/status", response_model=VehicleOut)
def change_vehicle_status(
    vehicle_id: uuid.UUID,
    body: VehicleStatusChange,
    auth: Annotated[Authorized, Depends(Require("fleet.vehicle.update_status"))],
    version: IfMatch,
    response: Response,
) -> VehicleOut:
    return _out(service.change_status(auth, vehicle_id, body, version), response)


@router.post("/vehicles/{vehicle_id}/retire", response_model=VehicleOut)
def retire_vehicle(
    vehicle_id: uuid.UUID,
    body: VehicleRetire,
    auth: Annotated[Authorized, Depends(Require("fleet.vehicle.deactivate"))],
    version: IfMatch,
    response: Response,
) -> VehicleOut:
    return _out(service.retire_vehicle(auth, vehicle_id, body, version), response)
