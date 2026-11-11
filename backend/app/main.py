"""Application FastAPI — monolithe modulaire MINEFLEET 360 (ADR-001)."""

import ipaddress
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.assignment.router import router as assignment_router
from app.audit.router import router as audit_router
from app.authz.routing import SecuredRoute
from app.billing.router import (
    own_subscription_router,
    subscription_router,
)
from app.billing.router import (
    router as billing_plans_router,
)
from app.core.clock import Clock, SystemClock
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.email import EmailSender, build_email_sender
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.request_context import RequestMeta, set_request_meta
from app.costs.router import router as costs_router
from app.dispatch.router import router as dispatch_router
from app.fleet.gps_alert_router import router as gps_alert_router
from app.fleet.gps_history import router as gps_history_router
from app.fleet.gps_live_router import router as gps_live_router
from app.fleet.gps_stream_router import router as gps_stream_router
from app.fleet.router import router as fleet_router
from app.fuel.anomalies import router as fuel_anomalies_router
from app.fuel.router import router as fuel_router
from app.hse.inspections import router as hse_inspections_router
from app.hse.router import router as hse_router
from app.identity.auth_service import AuthLimiters
from app.identity.router import auth_router, me_router, role_router, user_router
from app.legal.router import router as legal_router
from app.maintenance.parts_router import router as parts_router
from app.maintenance.purchase_order_router import router as purchase_order_router
from app.maintenance.reliability import router as reliability_router
from app.maintenance.replenishment_router import router as replenishment_router
from app.maintenance.router import router as maintenance_router
from app.maintenance.tyre_router import router as tyre_router
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

    # En production, la spécification OpenAPI n'est pas publiée : elle cartographie les permissions
    # de chaque route (x-permission) et élargit la surface de reconnaissance. Les environnements
    # locaux et de recette la conservent (contrat OpenAPI, intégration, support).
    expose_docs = settings.env != "production"
    app = FastAPI(
        title="MINEFLEET 360 API",
        version="0.1.0",
        openapi_url=f"{API_PREFIX}/openapi.json" if expose_docs else None,
        docs_url=f"{API_PREFIX}/docs" if expose_docs else None,
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
            allow_methods=["GET", "POST", "PATCH", "PUT"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "Idempotency-Key",
                "If-Match",
                "X-Request-ID",
            ],
            expose_headers=["ETag", "Idempotency-Replayed", "X-Request-ID", "Retry-After"],
        )

    health = APIRouter(route_class=SecuredRoute, tags=["santé"])

    @health.get("/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @health.get("/ready", include_in_schema=False)
    def database_readiness() -> Response:
        """Read-only DB readiness using the API's existing restricted database role."""
        try:
            with get_engine().connect() as connection:
                connection.execute(text("SELECT 1")).scalar_one()
        except (SQLAlchemyError, OSError, TimeoutError):
            # Do not reveal connection strings, roles or SQL errors publicly.
            return JSONResponse({"status": "unavailable"}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
        return JSONResponse({"status": "ok"})

    for router in (
        health,
        auth_router,
        me_router,
        platform_router,
        billing_plans_router,
        subscription_router,
        tenant_router,
        own_subscription_router,
        site_router,
        user_router,
        role_router,
        audit_router,
        fleet_router,
        gps_live_router,
        gps_stream_router,
        gps_history_router,
        gps_alert_router,
        workforce_router,
        assignment_router,
        dispatch_router,
        maintenance_router,
        reliability_router,
        tyre_router,
        costs_router,
        legal_router,
        parts_router,
        purchase_order_router,
        replenishment_router,
        fuel_router,
        fuel_anomalies_router,
        hse_router,
        hse_inspections_router,
    ):
        app.include_router(router, prefix=API_PREFIX)
    return app


app = create_app()
