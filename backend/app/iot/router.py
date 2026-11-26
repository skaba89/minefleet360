"""Authenticated registry endpoints; no machine ingestion or physical activation."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.http import Page, Pagination
from app.iot import service
from app.iot.models import IoTGateway, IoTManufacturer, IoTSensor
from app.iot.schemas import (
    GatewayCreate,
    GatewayOut,
    ManufacturerCreate,
    ManufacturerOut,
    SensorCreate,
    SensorOut,
)

router = APIRouter(prefix="/iot", tags=["iot"], route_class=SecuredRoute)

Read = Annotated[Authorized, Depends(Require("iot.registry.read"))]
Manage = Annotated[Authorized, Depends(Require("iot.registry.manage"))]
ManufacturerManage = Annotated[Authorized, Depends(Require("iot.manufacturer.create"))]


@router.get("/manufacturers", response_model=Page[ManufacturerOut])
def list_manufacturers(auth: Read, page: Pagination) -> Page[ManufacturerOut]:
    query = select(IoTManufacturer).where(IoTManufacturer.tenant_id == auth.tenant_id)
    total = auth.db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = auth.db.scalars(
        query.order_by(IoTManufacturer.name, IoTManufacturer.manufacturer_id)
        .offset(page.offset)
        .limit(page.page_size)
    )
    return Page(
        items=[ManufacturerOut.model_validate(row) for row in rows],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.post("/manufacturers", status_code=201, response_model=ManufacturerOut)
def create_manufacturer(body: ManufacturerCreate, auth: ManufacturerManage) -> ManufacturerOut:
    return service.create_manufacturer(auth, body)


@router.get("/gateways", response_model=Page[GatewayOut])
def list_gateways(auth: Read, page: Pagination) -> Page[GatewayOut]:
    query = select(IoTGateway).where(IoTGateway.tenant_id == auth.tenant_id)
    if not auth.scope.tenant_wide:
        query = query.where(IoTGateway.site_id.in_(auth.scope.site_ids))
    total = auth.db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = auth.db.scalars(
        query.order_by(IoTGateway.created_at, IoTGateway.gateway_id).offset(page.offset).limit(page.page_size)
    )
    return Page(
        items=[GatewayOut.model_validate(row) for row in rows],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.post("/gateways", status_code=201, response_model=GatewayOut)
def create_gateway(body: GatewayCreate, auth: Manage) -> GatewayOut:
    return service.create_gateway(auth, body)


@router.get("/sensors", response_model=Page[SensorOut])
def list_sensors(auth: Read, page: Pagination) -> Page[SensorOut]:
    query = select(IoTSensor).where(IoTSensor.tenant_id == auth.tenant_id)
    if not auth.scope.tenant_wide:
        query = query.where(IoTSensor.site_id.in_(auth.scope.site_ids))
    total = auth.db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = auth.db.scalars(
        query.order_by(IoTSensor.created_at, IoTSensor.sensor_id).offset(page.offset).limit(page.page_size)
    )
    return Page(
        items=[SensorOut.model_validate(row) for row in rows],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.post("/sensors", status_code=201, response_model=SensorOut)
def create_sensor(body: SensorCreate, auth: Manage) -> SensorOut:
    return service.create_sensor(auth, body)
