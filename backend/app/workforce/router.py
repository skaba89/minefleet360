import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.config import get_settings
from app.core.http import IfMatch, Page, Pagination, etag
from app.workforce import service
from app.workforce.schemas import (
    DriverCreate,
    DriverOut,
    DriverStatus,
    DriverStatusChange,
    DriverUpdate,
    ExpirationItem,
    LicenseCreate,
    LicenseOut,
    LicenseUpdate,
    QualificationCreate,
    QualificationOut,
    QualificationRevoke,
)

router = APIRouter(tags=["personnel"], route_class=SecuredRoute)


def _driver(auth: Authorized, driver_id: uuid.UUID, response: Response) -> DriverOut:
    driver = service.driver_in_scope(auth, driver_id)
    response.headers["ETag"] = etag(driver.row_version)
    return service.drivers_out(auth, [driver])[0]


@router.get("/drivers", response_model=Page[DriverOut], response_model_exclude_unset=True)
def list_drivers(
    auth: Annotated[Authorized, Depends(Require("workforce.driver.read"))],
    page: Pagination,
    site_id: uuid.UUID | None = None,
    status_filter: Annotated[DriverStatus | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(min_length=1, max_length=60)] = None,
) -> Page[DriverOut]:
    items, total = service.list_drivers(auth, page, site_id=site_id, status=status_filter, search=q)
    return Page(items=service.drivers_out(auth, items), page=page.page, page_size=page.page_size, total=total)


@router.get("/drivers/{driver_id}", response_model=DriverOut, response_model_exclude_unset=True)
def get_driver(
    driver_id: uuid.UUID,
    auth: Annotated[Authorized, Depends(Require("workforce.driver.read"))],
    response: Response,
) -> DriverOut:
    return _driver(auth, driver_id, response)


@router.post(
    "/drivers",
    status_code=status.HTTP_201_CREATED,
    response_model=DriverOut,
    response_model_exclude_unset=True,
)
def create_driver(
    body: DriverCreate,
    auth: Annotated[Authorized, Depends(Require("workforce.driver.create"))],
    response: Response,
) -> DriverOut:
    driver, warnings = service.create_driver(auth, body)
    response.headers["ETag"] = etag(driver.row_version)
    return service.driver_out(auth, driver, [], warnings)


@router.patch("/drivers/{driver_id}", response_model=DriverOut, response_model_exclude_unset=True)
def update_driver(
    driver_id: uuid.UUID,
    body: DriverUpdate,
    auth: Annotated[Authorized, Depends(Require("workforce.driver.update"))],
    version: IfMatch,
    response: Response,
) -> DriverOut:
    out = service.update_driver(auth, driver_id, body, version)
    response.headers["ETag"] = etag(out.row_version)
    return out


@router.post("/drivers/{driver_id}/status", response_model=DriverOut, response_model_exclude_unset=True)
def change_driver_status(
    driver_id: uuid.UUID,
    body: DriverStatusChange,
    auth: Annotated[Authorized, Depends(Require("workforce.driver.deactivate"))],
    version: IfMatch,
    response: Response,
) -> DriverOut:
    out = service.change_driver_status(auth, driver_id, body, version)
    response.headers["ETag"] = etag(out.row_version)
    return out


@router.get(
    "/drivers/{driver_id}/licenses", response_model=list[LicenseOut], response_model_exclude_unset=True
)
def list_licenses(
    driver_id: uuid.UUID, auth: Annotated[Authorized, Depends(Require("workforce.driver_license.read"))]
) -> list[LicenseOut]:
    return service.list_licenses(auth, driver_id)


@router.post(
    "/drivers/{driver_id}/licenses",
    status_code=status.HTTP_201_CREATED,
    response_model=LicenseOut,
    response_model_exclude_unset=True,
)
def create_license(
    driver_id: uuid.UUID,
    body: LicenseCreate,
    auth: Annotated[Authorized, Depends(Require("workforce.driver_license.manage"))],
    response: Response,
) -> LicenseOut:
    out = service.create_license(auth, driver_id, body)
    response.headers["ETag"] = etag(out.row_version)
    return out


@router.patch("/driver-licenses/{license_id}", response_model=LicenseOut, response_model_exclude_unset=True)
def update_license(
    license_id: uuid.UUID,
    body: LicenseUpdate,
    auth: Annotated[Authorized, Depends(Require("workforce.driver_license.manage"))],
    version: IfMatch,
    response: Response,
) -> LicenseOut:
    out = service.update_license(auth, license_id, body, version)
    response.headers["ETag"] = etag(out.row_version)
    return out


@router.get("/drivers/{driver_id}/qualifications", response_model=list[QualificationOut])
def list_qualifications(
    driver_id: uuid.UUID, auth: Annotated[Authorized, Depends(Require("workforce.driver_qualification.read"))]
) -> list[QualificationOut]:
    return service.list_qualifications(auth, driver_id)


@router.post(
    "/drivers/{driver_id}/qualifications",
    status_code=status.HTTP_201_CREATED,
    response_model=QualificationOut,
)
def create_qualification(
    driver_id: uuid.UUID,
    body: QualificationCreate,
    auth: Annotated[Authorized, Depends(Require("workforce.driver_qualification.manage"))],
    response: Response,
) -> QualificationOut:
    out = service.create_qualification(auth, driver_id, body)
    response.headers["ETag"] = etag(out.row_version)
    return out


@router.post("/driver-qualifications/{qualification_id}/revoke", response_model=QualificationOut)
def revoke_qualification(
    qualification_id: uuid.UUID,
    body: QualificationRevoke,
    auth: Annotated[Authorized, Depends(Require("workforce.driver_qualification.revoke"))],
    version: IfMatch,
    response: Response,
) -> QualificationOut:
    out = service.revoke_qualification(auth, qualification_id, body, version)
    response.headers["ETag"] = etag(out.row_version)
    return out


@router.get("/workforce/expirations", response_model=list[ExpirationItem])
def list_expirations(
    auth: Annotated[Authorized, Depends(Require("workforce.driver_license.read"))],
    within_days: Annotated[int | None, Query(ge=0, le=365)] = None,
) -> list[ExpirationItem]:
    return service.expirations(
        auth, within_days if within_days is not None else get_settings().expiry_warning_days
    )
