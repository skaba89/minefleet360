import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.authz.dependencies import Authorized, Require, SettingsDep
from app.authz.routing import SecuredRoute
from app.core.email import EmailSender
from app.core.http import IfMatch, Page, Pagination, etag
from app.organization import service
from app.organization.models import Site, Tenant
from app.organization.schemas import (
    SiteCreate,
    SiteOut,
    SiteUpdate,
    TenantCreate,
    TenantOut,
    TenantStatusChange,
    TenantSummary,
    TenantUpdate,
)

platform_router = APIRouter(prefix="/platform/tenants", tags=["plateforme"], route_class=SecuredRoute)
tenant_router = APIRouter(prefix="/tenant", tags=["tenant"], route_class=SecuredRoute)
site_router = APIRouter(prefix="/sites", tags=["sites"], route_class=SecuredRoute)


def get_email_sender(request: Request) -> EmailSender:
    sender: EmailSender = request.app.state.email_sender
    return sender


EmailDep = Annotated[EmailSender, Depends(get_email_sender)]


def _tenant_summary(tenant: Tenant) -> TenantSummary:
    return TenantSummary.model_validate(tenant, from_attributes=True)


def _tenant_out(tenant: Tenant, response: Response) -> TenantOut:
    response.headers["ETag"] = etag(tenant.row_version)
    return TenantOut.model_validate(tenant, from_attributes=True)


def _site_out(site: Site, response: Response | None = None) -> SiteOut:
    if response is not None:
        response.headers["ETag"] = etag(site.row_version)
    return SiteOut.model_validate(site, from_attributes=True)


# --- Plateforme (PLATFORM_ADMIN) ----------------------------------------------------------------------


@platform_router.post("", status_code=status.HTTP_201_CREATED, response_model=TenantSummary)
def create_tenant(
    body: TenantCreate,
    auth: Annotated[Authorized, Depends(Require("organization.tenant.create"))],
    settings: SettingsDep,
    email: EmailDep,
) -> TenantSummary:
    tenant, message = service.create_tenant(auth, body, settings)
    email.send(message)  # après COMMIT : un échec d'envoi laisse l'invitation renvoyable (US-1.04 A8)
    return _tenant_summary(tenant)


@platform_router.get("", response_model=Page[TenantSummary])
def list_tenants(
    auth: Annotated[Authorized, Depends(Require("organization.tenant.list"))], page: Pagination
) -> Page[TenantSummary]:
    items, total = service.list_tenants(auth.db, page)
    return Page(
        items=[_tenant_summary(t) for t in items], page=page.page, page_size=page.page_size, total=total
    )


@platform_router.get("/{tenant_id}", response_model=TenantSummary)
def get_tenant(
    tenant_id: uuid.UUID,
    auth: Annotated[Authorized, Depends(Require("organization.tenant.list"))],
    response: Response,
) -> TenantSummary:
    tenant = service.get_customer_tenant(auth.db, tenant_id)
    response.headers["ETag"] = etag(tenant.row_version)
    return _tenant_summary(tenant)


@platform_router.post("/{tenant_id}/suspend", response_model=TenantSummary)
def suspend_tenant(
    tenant_id: uuid.UUID,
    body: TenantStatusChange,
    auth: Annotated[Authorized, Depends(Require("organization.tenant.suspend"))],
    version: IfMatch,
) -> TenantSummary:
    return _tenant_summary(service.change_tenant_status(auth, tenant_id, version, "SUSPENDED", body.reason))


@platform_router.post("/{tenant_id}/reactivate", response_model=TenantSummary)
def reactivate_tenant(
    tenant_id: uuid.UUID,
    body: TenantStatusChange,
    auth: Annotated[Authorized, Depends(Require("organization.tenant.suspend"))],
    version: IfMatch,
) -> TenantSummary:
    return _tenant_summary(service.change_tenant_status(auth, tenant_id, version, "ACTIVE", body.reason))


# --- Tenant courant -----------------------------------------------------------------------------------


@tenant_router.get("", response_model=TenantOut)
def read_own_tenant(
    auth: Annotated[Authorized, Depends(Require("organization.tenant.read"))], response: Response
) -> TenantOut:
    return _tenant_out(service.get_own_tenant(auth), response)


@tenant_router.patch("", response_model=TenantOut)
def update_own_tenant(
    body: TenantUpdate,
    auth: Annotated[Authorized, Depends(Require("organization.tenant.update"))],
    version: IfMatch,
    response: Response,
) -> TenantOut:
    return _tenant_out(service.update_own_tenant(auth, body, version), response)


# --- Sites --------------------------------------------------------------------------------------------


@site_router.get("", response_model=Page[SiteOut])
def list_sites(
    auth: Annotated[Authorized, Depends(Require("organization.site.read"))],
    page: Pagination,
    status_filter: Annotated[Literal["ACTIVE", "INACTIVE"] | None, Query(alias="status")] = None,
) -> Page[SiteOut]:
    items, total = service.list_sites(auth, page, status_filter)
    return Page(items=[_site_out(s) for s in items], page=page.page, page_size=page.page_size, total=total)


@site_router.get("/{site_id}", response_model=SiteOut)
def get_site(
    site_id: uuid.UUID,
    auth: Annotated[Authorized, Depends(Require("organization.site.read"))],
    response: Response,
) -> SiteOut:
    return _site_out(service.get_site(auth, site_id), response)


@site_router.post("", status_code=status.HTTP_201_CREATED, response_model=SiteOut)
def create_site(
    body: SiteCreate,
    auth: Annotated[Authorized, Depends(Require("organization.site.create"))],
    response: Response,
) -> SiteOut:
    return _site_out(service.create_site(auth, body), response)


@site_router.patch("/{site_id}", response_model=SiteOut)
def update_site(
    site_id: uuid.UUID,
    body: SiteUpdate,
    auth: Annotated[Authorized, Depends(Require("organization.site.update"))],
    version: IfMatch,
    response: Response,
) -> SiteOut:
    return _site_out(service.update_site(auth, site_id, body, version), response)


@site_router.post("/{site_id}/deactivate", response_model=SiteOut)
def deactivate_site(
    site_id: uuid.UUID,
    auth: Annotated[Authorized, Depends(Require("organization.site.deactivate"))],
    version: IfMatch,
    response: Response,
) -> SiteOut:
    return _site_out(service.change_site_status(auth, site_id, version, "INACTIVE"), response)


@site_router.post("/{site_id}/reactivate", response_model=SiteOut)
def reactivate_site(
    site_id: uuid.UUID,
    auth: Annotated[Authorized, Depends(Require("organization.site.deactivate"))],
    version: IfMatch,
    response: Response,
) -> SiteOut:
    return _site_out(service.change_site_status(auth, site_id, version, "ACTIVE"), response)
