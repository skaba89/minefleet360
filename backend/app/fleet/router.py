import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.http import IfMatch, Page, Pagination, etag
from app.fleet import records, service
from app.fleet.models import Vehicle
from app.fleet.schemas import (
    CategoryDocumentsIn,
    CategoryDocumentsOut,
    DocumentCreate,
    DocumentOut,
    DocumentWithdraw,
    MeterKind,
    MeterReadingCreate,
    MeterReadingOut,
    MeterReset,
    StatusHistoryOut,
    VehicleCategoryOut,
    VehicleCreate,
    VehicleDocumentsOut,
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


@router.get(
    "/vehicles/{vehicle_id}/status-history",
    response_model=list[StatusHistoryOut],
    response_model_exclude_unset=True,
)
def vehicle_status_history(
    vehicle_id: uuid.UUID, auth: Annotated[Authorized, Depends(Require("fleet.vehicle.read"))]
) -> list[StatusHistoryOut]:
    return service.status_history(auth, vehicle_id)


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


# --- Compteurs et documents (lot 2c) --------------------------------------------------------------------

DocumentRead = Annotated[Authorized, Depends(Require("fleet.document.read"))]
DocumentManage = Annotated[Authorized, Depends(Require("fleet.document.manage"))]


@router.get("/vehicles/{vehicle_id}/meter-readings", response_model=Page[MeterReadingOut])
def list_meter_readings(
    vehicle_id: uuid.UUID,
    auth: Annotated[Authorized, Depends(Require("fleet.meter.read"))],
    page: Pagination,
    meter_kind: MeterKind | None = None,
) -> Page[MeterReadingOut]:
    items, total = records.list_readings(auth, vehicle_id, page, meter_kind=meter_kind)
    return Page(items=items, page=page.page, page_size=page.page_size, total=total)


@router.post(
    "/vehicles/{vehicle_id}/meter-readings",
    status_code=status.HTTP_201_CREATED,
    response_model=MeterReadingOut,
)
def record_meter_reading(
    vehicle_id: uuid.UUID,
    body: MeterReadingCreate,
    auth: Annotated[Authorized, Depends(Require("fleet.meter.record"))],
) -> MeterReadingOut:
    return records.record_reading(auth, vehicle_id, body)


@router.post(
    "/vehicles/{vehicle_id}/meter-resets", status_code=status.HTTP_201_CREATED, response_model=MeterReadingOut
)
def reset_vehicle_meter(
    vehicle_id: uuid.UUID,
    body: MeterReset,
    auth: Annotated[Authorized, Depends(Require("fleet.meter.reset"))],
) -> MeterReadingOut:
    return records.reset_meter(auth, vehicle_id, body)


@router.get("/vehicles/{vehicle_id}/documents", response_model=VehicleDocumentsOut)
def list_vehicle_documents(vehicle_id: uuid.UUID, auth: DocumentRead) -> VehicleDocumentsOut:
    return records.list_documents(auth, vehicle_id)


@router.get("/vehicle-documents", response_model=list[DocumentOut])
def due_vehicle_documents(
    auth: DocumentRead,
    site_id: uuid.UUID | None = None,
    within_days: Annotated[int, Query(ge=0, le=365)] = 45,
) -> list[DocumentOut]:
    return records.due_documents(auth, site_id=site_id, within_days=within_days)


@router.post(
    "/vehicles/{vehicle_id}/documents", status_code=status.HTTP_201_CREATED, response_model=DocumentOut
)
def create_vehicle_document(
    vehicle_id: uuid.UUID, body: DocumentCreate, auth: DocumentManage, response: Response
) -> DocumentOut:
    out = records.create_document(auth, vehicle_id, body)
    response.headers["ETag"] = etag(out.row_version)
    return out


@router.post("/vehicle-documents/{vehicle_document_id}/withdraw", response_model=DocumentOut)
def withdraw_vehicle_document(
    vehicle_document_id: uuid.UUID,
    body: DocumentWithdraw,
    auth: DocumentManage,
    version: IfMatch,
    response: Response,
) -> DocumentOut:
    out = records.withdraw_document(auth, vehicle_document_id, body.reason_code, version)
    response.headers["ETag"] = etag(out.row_version)
    return out


@router.get("/vehicle-categories/{category_id}/required-documents", response_model=CategoryDocumentsOut)
def get_category_documents(
    category_id: uuid.UUID,
    auth: Annotated[Authorized, Depends(Require("fleet.vehicle_category.read"))],
) -> CategoryDocumentsOut:
    return records.category_documents(auth, category_id)


@router.put("/vehicle-categories/{category_id}/required-documents", response_model=CategoryDocumentsOut)
def set_category_documents(
    category_id: uuid.UUID,
    body: CategoryDocumentsIn,
    auth: Annotated[Authorized, Depends(Require("fleet.vehicle_category.manage"))],
) -> CategoryDocumentsOut:
    return records.set_category_documents(auth, category_id, list(body.doc_types))
