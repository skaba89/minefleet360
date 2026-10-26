import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import AwareDatetime

from app.assignment import service
from app.assignment.schemas import (
    AssignmentCancel,
    AssignmentComplete,
    AssignmentCreate,
    AssignmentOut,
    AssignmentStatus,
    AssignmentSuspend,
    Compliance,
)
from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.http import IfMatch, Page, Pagination, etag

router = APIRouter(tags=["affectations"], route_class=SecuredRoute)

Read = Annotated[Authorized, Depends(Require("assignment.vehicle_assignment.read"))]
Update = Annotated[Authorized, Depends(Require("assignment.vehicle_assignment.update"))]
End = Annotated[Authorized, Depends(Require("assignment.vehicle_assignment.end"))]


def _with_etag(out: AssignmentOut, response: Response) -> AssignmentOut:
    response.headers["ETag"] = etag(out.row_version)
    return out


def _page(items: list[AssignmentOut], total: int, page: Pagination) -> Page[AssignmentOut]:
    return Page(items=items, page=page.page, page_size=page.page_size, total=total)


@router.get("/vehicle-assignments", response_model=Page[AssignmentOut], response_model_exclude_unset=True)
def list_assignments(
    auth: Read,
    page: Pagination,
    site_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    driver_id: uuid.UUID | None = None,
    status_filter: Annotated[AssignmentStatus | None, Query(alias="status")] = None,
    at: AwareDatetime | None = None,
    compliance: Compliance | None = None,
) -> Page[AssignmentOut]:
    items, total = service.list_assignments(
        auth,
        page,
        site_id=site_id,
        vehicle_id=vehicle_id,
        driver_id=driver_id,
        status=status_filter,
        at=at,
        compliance_filter=compliance,
    )
    return _page(items, total, page)


@router.get(
    "/vehicle-assignments/{vehicle_assignment_id}",
    response_model=AssignmentOut,
    response_model_exclude_unset=True,
)
def get_assignment(vehicle_assignment_id: uuid.UUID, auth: Read, response: Response) -> AssignmentOut:
    assignment = service.assignment_in_scope(auth, vehicle_assignment_id)
    return _with_etag(service.assignments_out(auth, [assignment])[0], response)


@router.get(
    "/vehicles/{vehicle_id}/assignments",
    response_model=Page[AssignmentOut],
    response_model_exclude_unset=True,
)
def vehicle_assignments(vehicle_id: uuid.UUID, auth: Read, page: Pagination) -> Page[AssignmentOut]:
    service.ensure_vehicle_visible(auth, vehicle_id)
    items, total = service.list_assignments(auth, page, vehicle_id=vehicle_id)
    return _page(items, total, page)


@router.get(
    "/drivers/{driver_id}/assignments", response_model=Page[AssignmentOut], response_model_exclude_unset=True
)
def driver_assignments(driver_id: uuid.UUID, auth: Read, page: Pagination) -> Page[AssignmentOut]:
    service.ensure_driver_visible(auth, driver_id)
    items, total = service.list_assignments(auth, page, driver_id=driver_id)
    return _page(items, total, page)


@router.post(
    "/vehicle-assignments",
    status_code=status.HTTP_201_CREATED,
    response_model=AssignmentOut,
    response_model_exclude_unset=True,
)
def create_assignment(
    body: AssignmentCreate,
    auth: Annotated[Authorized, Depends(Require("assignment.vehicle_assignment.create"))],
    response: Response,
) -> AssignmentOut:
    return _with_etag(service.create_assignment(auth, body), response)


@router.post(
    "/vehicle-assignments/{vehicle_assignment_id}/activate",
    response_model=AssignmentOut,
    response_model_exclude_unset=True,
)
def activate_assignment(
    vehicle_assignment_id: uuid.UUID, auth: Update, version: IfMatch, response: Response
) -> AssignmentOut:
    return _with_etag(service.activate_assignment(auth, vehicle_assignment_id, version), response)


@router.post(
    "/vehicle-assignments/{vehicle_assignment_id}/suspend",
    response_model=AssignmentOut,
    response_model_exclude_unset=True,
)
def suspend_assignment(
    vehicle_assignment_id: uuid.UUID,
    body: AssignmentSuspend,
    auth: Update,
    version: IfMatch,
    response: Response,
) -> AssignmentOut:
    return _with_etag(service.suspend_assignment(auth, vehicle_assignment_id, body, version), response)


@router.post(
    "/vehicle-assignments/{vehicle_assignment_id}/resume",
    response_model=AssignmentOut,
    response_model_exclude_unset=True,
)
def resume_assignment(
    vehicle_assignment_id: uuid.UUID, auth: Update, version: IfMatch, response: Response
) -> AssignmentOut:
    return _with_etag(service.resume_assignment(auth, vehicle_assignment_id, version), response)


@router.post(
    "/vehicle-assignments/{vehicle_assignment_id}/complete",
    response_model=AssignmentOut,
    response_model_exclude_unset=True,
)
def complete_assignment(
    vehicle_assignment_id: uuid.UUID,
    body: AssignmentComplete,
    auth: End,
    version: IfMatch,
    response: Response,
) -> AssignmentOut:
    return _with_etag(service.complete_assignment(auth, vehicle_assignment_id, body, version), response)


@router.post(
    "/vehicle-assignments/{vehicle_assignment_id}/cancel",
    response_model=AssignmentOut,
    response_model_exclude_unset=True,
)
def cancel_assignment(
    vehicle_assignment_id: uuid.UUID, body: AssignmentCancel, auth: End, version: IfMatch, response: Response
) -> AssignmentOut:
    return _with_etag(service.cancel_assignment(auth, vehicle_assignment_id, body, version), response)
