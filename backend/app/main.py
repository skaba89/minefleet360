"""Application FastAPI — monolithe modulaire MINEFLEET 360 (ADR-001)."""

import ipaddress
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.assignment.router import router as assignment_router
from app.audit.router import router as audit_router
from app.authz.routing import SecuredRoute
from app.core.clock import Clock, SystemClock
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.email import EmailSender, build_email_sender
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.request_context import RequestMeta, set_request_meta
from app.fleet.router import router as fleet_router
from app.identity.auth_service import AuthLimiters
from app.identity.router import auth_router, me_router, role_router, user_router
from app.organization.router import platform_router, site_router, tenant_router
from app.workforce.router import router as workforce_router

API_PREFIX = "/api/v1"


def check_database_role() -> None:
    """DBT-48 : l'API refuse de démarrer si son rôle peut contourner la RLS."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
        if row.rolsuper or row.rolbypassrls:
            raise RuntimeError("Le rôle applicatif ne doit être ni super-utilisateur ni BYPASSRLS")


def _request_id(header: str | None) -> uuid.UUID:
    try:
        return uuid.UUID(header) if header else uuid.uuid4()
    except ValueError:
        return uuid.uuid4()


def _client_ip(request: Request) -> str | None:
    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None


def create_app(clock: Clock | None = None, email_sender: EmailSender | None = None) -> FastAPI:
    settings = get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        check_database_role()
        yield

    app = FastAPI(
        title="MINEFLEET 360 API",
        version="0.1.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.clock = clock or SystemClock()
    app.state.email_sender = email_sender or build_email_sender(settings)
    app.state.auth_limiters = AuthLimiters(settings)

    install_error_handlers(app)

    @app.middleware("http")
    async def request_meta(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        meta = RequestMeta(
            request_id=_request_id(request.headers.get("x-request-id")),
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        set_request_meta(meta)
        response = await call_next(request)
        response.headers["X-Request-ID"] = str(meta.request_id)
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    if settings.allowed_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origin_list,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH"],
            allow_headers=["Authorization", "Content-Type", "If-Match", "X-Request-ID"],
            expose_headers=["ETag", "X-Request-ID", "Retry-After"],
        )

    health = APIRouter(route_class=SecuredRoute, tags=["santé"])

    @health.get("/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    for router in (
        health,
        auth_router,
        me_router,
        platform_router,
        tenant_router,
        site_router,
        user_router,
        role_router,
        audit_router,
        fleet_router,
        workforce_router,
        assignment_router,
    ):
        app.include_router(router, prefix=API_PREFIX)
    return app


app = create_app()
