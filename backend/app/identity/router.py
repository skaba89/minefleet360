import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, Response, status
from sqlalchemy import select

from app.authz.dependencies import Authorized, ClockDep, DbSession, Require, SettingsDep, load_grants
from app.authz.routing import SecuredRoute
from app.core.config import Settings
from app.core.errors import AppError
from app.core.http import IfMatch, Page, Pagination, etag
from app.identity import auth_service, service
from app.identity.auth_service import AuthLimiters, IssuedSession
from app.identity.models import UserAccount
from app.identity.schemas import (
    ChangePasswordRequest,
    GrantOut,
    LoginRequest,
    MeOut,
    PlatformLoginRequest,
    ResetRequest,
    RoleAssignmentCreate,
    RoleAssignmentOut,
    RoleOut,
    SessionUser,
    TokenPasswordRequest,
    TokenResponse,
    UserInvite,
    UserOut,
    UserUpdate,
)
from app.organization.models import Tenant
from app.organization.router import EmailDep

REFRESH_COOKIE = "mf_refresh"
COOKIE_PATH = "/api/v1/auth"

auth_router = APIRouter(prefix="/auth", tags=["authentification"], route_class=SecuredRoute)
me_router = APIRouter(prefix="/me", tags=["mon compte"], route_class=SecuredRoute)
user_router = APIRouter(prefix="/users", tags=["utilisateurs"], route_class=SecuredRoute)
role_router = APIRouter(tags=["rôles"], route_class=SecuredRoute)


def get_limiters(request: Request) -> AuthLimiters:
    limiters: AuthLimiters = request.app.state.auth_limiters
    return limiters


LimitersDep = Annotated[AuthLimiters, Depends(get_limiters)]
RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]


def _check_origin(origin: str | None, settings: Settings) -> None:
    """Protection CSRF du seul point d'entrée à cookie (ADR-003) : SameSite=Strict + Origin autorisée."""
    if origin is not None and origin not in settings.allowed_origin_list:
        raise AppError("AUTH_REQUIRED")


def _token_response(
    issued: IssuedSession, response: Response, settings: Settings, clock: ClockDep
) -> TokenResponse:
    max_age = max(0, int((issued.session_expires_at - clock.now()).total_seconds()))
    response.set_cookie(
        REFRESH_COOKIE,
        issued.refresh_cookie,
        max_age=max_age,
        path=COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(
        access_token=issued.access_token,
        expires_in=issued.expires_in,
        user=SessionUser(
            user_account_id=issued.user_id,
            display_name=issued.display_name,
            workspace_code=issued.workspace_code,
        ),
    )


def _clear_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        REFRESH_COOKIE, path=COOKIE_PATH, httponly=True, secure=settings.cookie_secure, samesite="strict"
    )


# --- Routes publiques (public_routes de authz_matrix.yaml) -------------------------------------------


@auth_router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
    limiters: LimitersDep,
    response: Response,
) -> TokenResponse:
    issued = auth_service.login(
        db,
        code=body.workspace_code,
        email=body.email,
        password=body.password,
        kind="CUSTOMER",
        clock=clock,
        settings=settings,
        limiters=limiters,
    )
    return _token_response(issued, response, settings, clock)


@auth_router.post("/platform/login", response_model=TokenResponse)
def platform_login(
    body: PlatformLoginRequest,
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
    limiters: LimitersDep,
    response: Response,
) -> TokenResponse:
    issued = auth_service.login(
        db,
        code=settings.platform_tenant_code,
        email=body.email,
        password=body.password,
        kind="PLATFORM",
        clock=clock,
        settings=settings,
        limiters=limiters,
    )
    return _token_response(issued, response, settings, clock)


@auth_router.post("/refresh", response_model=TokenResponse)
def refresh(
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
    response: Response,
    refresh_cookie: RefreshCookie = None,
    origin: Annotated[str | None, Header()] = None,
) -> TokenResponse:
    _check_origin(origin, settings)
    issued = auth_service.refresh(db, raw_cookie=refresh_cookie, clock=clock, settings=settings)
    return _token_response(issued, response, settings, clock)


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
    response: Response,
    refresh_cookie: RefreshCookie = None,
    origin: Annotated[str | None, Header()] = None,
) -> None:
    _check_origin(origin, settings)
    auth_service.logout(db, raw_cookie=refresh_cookie, clock=clock)
    _clear_cookie(response, settings)


@auth_router.post("/invitations/accept", status_code=status.HTTP_204_NO_CONTENT)
def accept_invitation(
    body: TokenPasswordRequest, db: DbSession, clock: ClockDep, settings: SettingsDep, limiters: LimitersDep
) -> None:
    auth_service.accept_invitation(
        db, raw_token=body.token, password=body.password, clock=clock, settings=settings, limiters=limiters
    )


@auth_router.post("/password/reset-request", status_code=status.HTTP_202_ACCEPTED)
def password_reset_request(
    body: ResetRequest,
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
    limiters: LimitersDep,
    email: EmailDep,
) -> dict[str, str]:
    message = auth_service.request_password_reset(
        db, code=body.workspace_code, email=body.email, clock=clock, settings=settings, limiters=limiters
    )
    if message is not None:
        email.send(message)
    return {"message_fr": "Si un compte correspond, un lien de réinitialisation a été envoyé."}


@auth_router.post("/password/reset-confirm", status_code=status.HTTP_204_NO_CONTENT)
def password_reset_confirm(
    body: TokenPasswordRequest, db: DbSession, clock: ClockDep, settings: SettingsDep, limiters: LimitersDep
) -> None:
    auth_service.confirm_password_reset(
        db, raw_token=body.token, password=body.password, clock=clock, settings=settings, limiters=limiters
    )


# --- Mon compte ---------------------------------------------------------------------------------------


@me_router.get("", response_model=MeOut)
def read_me(auth: Annotated[Authorized, Depends(Require("identity.user.update_self"))]) -> MeOut:
    user = auth.db.execute(
        select(UserAccount).where(UserAccount.user_account_id == auth.user_id)
    ).scalar_one()
    tenant = auth.db.execute(select(Tenant).where(Tenant.tenant_id == auth.tenant_id)).scalar_one()
    grants = load_grants(auth.db, auth.user_id, auth.clock)
    return MeOut(
        user_account_id=user.user_account_id,
        display_name=user.display_name,
        email=user.email,
        workspace_code=tenant.code,
        tenant_display_name=tenant.display_name,
        timezone=tenant.default_timezone,
        grants=[GrantOut(role_code=g.role_code, scope_type=g.scope_type, site_id=g.site_id) for g in grants],
    )


@me_router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordRequest,
    auth: Annotated[Authorized, Depends(Require("identity.user.update_self"))],
    settings: SettingsDep,
    limiters: LimitersDep,
) -> None:
    auth_service.change_own_password(
        auth.db,
        user_id=auth.user_id,
        session_id=auth.principal.session_id,
        current=body.current_password,
        new=body.new_password,
        clock=auth.clock,
        settings=settings,
        limiters=limiters,
    )


# --- Utilisateurs -------------------------------------------------------------------------------------


@user_router.get("", response_model=Page[UserOut], response_model_exclude_unset=True)
def list_users(
    auth: Annotated[Authorized, Depends(Require("identity.user.read"))],
    page: Pagination,
    status_filter: Annotated[Literal["INVITED", "ACTIVE", "DISABLED"] | None, Query(alias="status")] = None,
) -> Page[UserOut]:
    items, total = service.list_users(auth, page, status_filter)
    return Page(
        items=[service.user_out(u, auth.scope) for u in items],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@user_router.get("/{user_id}", response_model=UserOut, response_model_exclude_unset=True)
def get_user(
    user_id: uuid.UUID,
    auth: Annotated[Authorized, Depends(Require("identity.user.read"))],
    response: Response,
) -> UserOut:
    user = service.get_user(auth, user_id)
    response.headers["ETag"] = etag(user.row_version)
    return service.user_out(user, auth.scope)


@user_router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=UserOut, response_model_exclude_unset=True
)
def invite_user(
    body: UserInvite,
    auth: Annotated[Authorized, Depends(Require("identity.user.create"))],
    settings: SettingsDep,
    email: EmailDep,
) -> UserOut:
    user, message = service.invite_user(auth, body, settings)
    email.send(message)
    return service.user_out(user, auth.scope)


@user_router.post("/{user_id}/resend-invitation", status_code=status.HTTP_202_ACCEPTED)
def resend_invitation(
    user_id: uuid.UUID,
    auth: Annotated[Authorized, Depends(Require("identity.user.create"))],
    settings: SettingsDep,
    email: EmailDep,
) -> dict[str, str]:
    email.send(service.resend_invitation(auth, user_id, settings))
    return {"message_fr": "Invitation renvoyée."}


@user_router.patch("/{user_id}", response_model=UserOut, response_model_exclude_unset=True)
def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    auth: Annotated[Authorized, Depends(Require("identity.user.update"))],
    version: IfMatch,
    response: Response,
) -> UserOut:
    user = service.update_user(auth, user_id, body, version)
    response.headers["ETag"] = etag(user.row_version)
    return service.user_out(user, auth.scope)


@user_router.post("/{user_id}/deactivate", response_model=UserOut, response_model_exclude_unset=True)
def deactivate_user(
    user_id: uuid.UUID,
    auth: Annotated[Authorized, Depends(Require("identity.user.deactivate"))],
    version: IfMatch,
) -> UserOut:
    return service.user_out(service.change_user_status(auth, user_id, version, deactivate=True), auth.scope)


@user_router.post("/{user_id}/reactivate", response_model=UserOut, response_model_exclude_unset=True)
def reactivate_user(
    user_id: uuid.UUID,
    auth: Annotated[Authorized, Depends(Require("identity.user.deactivate"))],
    version: IfMatch,
) -> UserOut:
    return service.user_out(service.change_user_status(auth, user_id, version, deactivate=False), auth.scope)


@user_router.post("/{user_id}/reset-credentials", status_code=status.HTTP_202_ACCEPTED)
def reset_credentials(
    user_id: uuid.UUID,
    auth: Annotated[Authorized, Depends(Require("identity.user.reset_credentials"))],
    settings: SettingsDep,
    email: EmailDep,
) -> dict[str, str]:
    email.send(service.admin_reset_credentials(auth, user_id, settings))
    return {"message_fr": "Lien de réinitialisation envoyé."}


# --- Rôles et attributions ----------------------------------------------------------------------------


@role_router.get("/roles", response_model=list[RoleOut])
def list_roles(auth: Annotated[Authorized, Depends(Require("identity.role.read"))]) -> list[RoleOut]:
    return service.list_roles(auth)


@role_router.get("/role-assignments", response_model=Page[RoleAssignmentOut])
def list_assignments(
    auth: Annotated[Authorized, Depends(Require("identity.role_assignment.read"))],
    page: Pagination,
    user_id: uuid.UUID | None = None,
    include_revoked: bool = False,
) -> Page[RoleAssignmentOut]:
    items, total = service.list_assignments(auth, page, user_id, include_revoked)
    return Page(
        items=[RoleAssignmentOut.model_validate(a, from_attributes=True) for a in items],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@role_router.post("/role-assignments", status_code=status.HTTP_201_CREATED, response_model=RoleAssignmentOut)
def create_assignment(
    body: RoleAssignmentCreate,
    auth: Annotated[Authorized, Depends(Require("identity.role_assignment.create"))],
    response: Response,
) -> RoleAssignmentOut:
    assignment = service.create_assignment(auth, body)
    response.headers["ETag"] = etag(assignment.row_version)
    return RoleAssignmentOut.model_validate(assignment, from_attributes=True)


@role_router.post("/role-assignments/{assignment_id}/revoke", response_model=RoleAssignmentOut)
def revoke_assignment(
    assignment_id: uuid.UUID,
    auth: Annotated[Authorized, Depends(Require("identity.role_assignment.revoke"))],
    version: IfMatch,
) -> RoleAssignmentOut:
    return RoleAssignmentOut.model_validate(
        service.revoke_assignment(auth, assignment_id, version), from_attributes=True
    )
