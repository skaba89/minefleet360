import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.http import IfMatch, etag
from app.partners import service
from app.partners.models import Subcontractor
from app.partners.schemas import (
    SubcontractorCreate,
    SubcontractorOut,
    SubcontractorStatus,
    SubcontractorUpdate,
)

router = APIRouter(tags=["partners"], route_class=SecuredRoute)
SubcontractorRead = Annotated[Authorized, Depends(Require("partner.subcontractor.read"))]
SubcontractorManage = Annotated[Authorized, Depends(Require("partner.subcontractor.manage"))]


def _out(subcontractor: Subcontractor, response: Response | None = None) -> SubcontractorOut:
    if response is not None:
        response.headers["ETag"] = etag(subcontractor.row_version)
    return SubcontractorOut.model_validate(subcontractor, from_attributes=True)


@router.get("/subcontractors", response_model=list[SubcontractorOut])
def list_subcontractors(
    auth: SubcontractorRead, status: SubcontractorStatus | None = None
) -> list[SubcontractorOut]:
    return [_out(s) for s in service.list_subcontractors(auth, status=status)]


@router.post("/subcontractors", status_code=status.HTTP_201_CREATED, response_model=SubcontractorOut)
def create_subcontractor(
    body: SubcontractorCreate, auth: SubcontractorManage, response: Response
) -> SubcontractorOut:
    return _out(service.create_subcontractor(auth, body), response)


@router.patch("/subcontractors/{subcontractor_id}", response_model=SubcontractorOut)
def update_subcontractor(
    subcontractor_id: uuid.UUID,
    body: SubcontractorUpdate,
    auth: SubcontractorManage,
    version: IfMatch,
    response: Response,
) -> SubcontractorOut:
    return _out(service.update_subcontractor(auth, subcontractor_id, body, version), response)
