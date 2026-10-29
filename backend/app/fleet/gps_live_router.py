import uuid
from typing import Annotated

from anyio import fail_after
from fastapi import APIRouter, Depends, Header, Request, Response
from starlette.concurrency import run_in_threadpool

from app.authz.dependencies import Authorized, ClockDep, DbSession, Require, reject_unknown_query
from app.authz.routing import SecuredRoute
from app.core.errors import AppError
from app.core.http import Page, Pagination
from app.core.security import parse_composite_token
from app.fleet import gps_live_service as service
from app.fleet.gps_live_schemas import (
    DriverAccountIn,
    DriverAccountOut,
    GpsVehicleOut,
    PhonePointIn,
    PhoneShareOut,
    PhoneStartIn,
    TrackerCreateIn,
    TrackerOut,
    TrackerProvisionOut,
)
from app.fleet.gps_payload_ingestion import (
    MAX_GPS_PAYLOAD_BYTES,
)
from app.fleet.gps_tracker_ingest import check_source_rate, ingest_tracker

router = APIRouter(tags=["géolocalisation"], route_class=SecuredRoute)
ShareAuth = Annotated[Authorized, Depends(Require("fleet.gps.share"))]
ManageAuth = Annotated[Authorized, Depends(Require("fleet.gps.manage"))]
LinkAuth = Annotated[Authorized, Depends(Require("workforce.driver.link_account"))]


@router.get("/me/gps/vehicles", response_model=Page[GpsVehicleOut])
def sharing_vehicles(auth: ShareAuth, page: Pagination) -> Page[GpsVehicleOut]:
    items, total = service.sharing_vehicles(auth, page)
    return Page(
        items=[GpsVehicleOut.model_validate(v) for v in items],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.post("/me/gps/shares", response_model=PhoneShareOut, status_code=201)
def start_phone(body: PhoneStartIn, auth: ShareAuth) -> PhoneShareOut:
    return service.start_phone(auth, body)


@router.post("/me/gps/shares/{share_id}/positions", status_code=204)
def phone_point(share_id: uuid.UUID, body: PhonePointIn, auth: ShareAuth) -> Response:
    service.phone_point(auth, share_id, body)
    return Response(status_code=204)


@router.post("/me/gps/shares/{share_id}/stop", status_code=204)
def stop_phone(share_id: uuid.UUID, auth: ShareAuth) -> Response:
    service.stop_phone(auth, share_id)
    return Response(status_code=204)


@router.get("/vehicles/{vehicle_id}/gps/tracker", response_model=TrackerOut | None)
def tracker(vehicle_id: uuid.UUID, auth: ManageAuth) -> TrackerOut | None:
    binding = service.tracker_for_vehicle(auth, vehicle_id)
    return TrackerOut.model_validate(binding) if binding is not None else None


@router.post("/vehicles/{vehicle_id}/gps/tracker", response_model=TrackerProvisionOut, status_code=201)
def provision_tracker(vehicle_id: uuid.UUID, body: TrackerCreateIn, auth: ManageAuth) -> TrackerProvisionOut:
    return service.provision_tracker(auth, vehicle_id, body)


@router.post("/vehicles/{vehicle_id}/gps/tracker/revoke", status_code=204)
def revoke_tracker(vehicle_id: uuid.UUID, auth: ManageAuth) -> Response:
    service.revoke_tracker(auth, vehicle_id)
    return Response(status_code=204)


@router.get("/drivers/{driver_id}/gps-account", response_model=DriverAccountOut)
def driver_account(driver_id: uuid.UUID, auth: LinkAuth) -> DriverAccountOut:
    return DriverAccountOut(user_account_id=service.driver_account(auth, driver_id))


@router.post("/drivers/{driver_id}/gps-account", response_model=DriverAccountOut)
def link_driver_account(driver_id: uuid.UUID, body: DriverAccountIn, auth: LinkAuth) -> DriverAccountOut:
    return DriverAccountOut(user_account_id=service.driver_account(auth, driver_id, body))


@router.post("/gps/telemetry", status_code=204)
async def tracker_telemetry(
    request: Request,
    db: DbSession,
    clock: ClockDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Authentification machine dédiée : jamais un compte utilisateur ou un tenant fourni en JSON."""
    now = clock.now()
    await run_in_threadpool(check_source_rate, now)
    raw = (
        authorization.removeprefix("Bearer gps_")
        if authorization and authorization.startswith("Bearer gps_")
        else None
    )
    credential = parse_composite_token(raw)
    if credential is None:
        raise AppError("AUTH_REQUIRED")
    reject_unknown_query(request)
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise AppError("VALIDATION_ERROR")
    payload = bytearray()
    try:
        with fail_after(10):
            async for chunk in request.stream():
                if len(payload) + len(chunk) > MAX_GPS_PAYLOAD_BYTES:
                    raise AppError("VALIDATION_ERROR")
                payload.extend(chunk)
    except TimeoutError:
        raise AppError("VALIDATION_ERROR", message_fr="Réception GPS trop lente.") from None
    # Aucune transaction ni verrou métier pendant l'attente du corps HTTP.
    await run_in_threadpool(ingest_tracker, db, credential, bytes(payload), now)
    return Response(status_code=204)
