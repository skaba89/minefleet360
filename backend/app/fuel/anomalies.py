"""Traitement des dossiers d'anomalie carburant, strictement limité au tenant et au site."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.audit.contracts import record
from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.errors import AppError
from app.core.http import Page, Pagination, StrictModel
from app.fuel.models import FuelPump, FuelPumpAnomalyCase, FuelPumpAnomalyEvent, FuelPumpMeterReading

router = APIRouter(tags=["carburant"], route_class=SecuredRoute)
Read = Annotated[Authorized, Depends(Require("fuel.anomaly.read"))]
Manage = Annotated[Authorized, Depends(Require("fuel.anomaly.manage"))]
EventType = Literal["ACKNOWLEDGED", "JUSTIFIED", "CLOSED"]


class AnomalyOpen(StrictModel):
    start_reading_id: uuid.UUID
    end_reading_id: uuid.UUID


class AnomalyEventCreate(StrictModel):
    event_type: EventType
    justification: str = Field(min_length=10, max_length=2000)


class AnomalyCaseOut(BaseModel):
    fuel_pump_anomaly_case_id: uuid.UUID
    fuel_pump_id: uuid.UUID
    site_id: uuid.UUID
    start_reading_id: uuid.UUID
    end_reading_id: uuid.UUID
    created_by: uuid.UUID


class AnomalyEventOut(BaseModel):
    fuel_pump_anomaly_event_id: uuid.UUID
    fuel_pump_anomaly_case_id: uuid.UUID
    event_type: EventType
    justification: str
    actor_user_id: uuid.UUID


def _case(auth: Authorized, case_id: uuid.UUID, *, lock: bool = False) -> FuelPumpAnomalyCase:
    query = select(FuelPumpAnomalyCase).where(
        FuelPumpAnomalyCase.tenant_id == auth.tenant_id,
        FuelPumpAnomalyCase.fuel_pump_anomaly_case_id == case_id,
    )
    if lock:
        query = query.with_for_update()
    case = auth.db.scalar(query)
    if case is None or not auth.scope.covers_site(case.site_id):
        raise AppError("NOT_FOUND")
    return case


@router.post(
    "/fuel/pumps/{fuel_pump_id}/anomaly-cases",
    response_model=AnomalyCaseOut,
    status_code=status.HTTP_201_CREATED,
)
def open_anomaly_case(fuel_pump_id: uuid.UUID, body: AnomalyOpen, auth: Manage) -> AnomalyCaseOut:
    pump = auth.db.scalar(
        select(FuelPump).where(FuelPump.tenant_id == auth.tenant_id, FuelPump.fuel_pump_id == fuel_pump_id)
    )
    if pump is None or not auth.scope.covers_site(pump.site_id):
        raise AppError("NOT_FOUND")
    if body.start_reading_id == body.end_reading_id:
        raise AppError("CONFLICT")
    readings = auth.db.scalars(
        select(FuelPumpMeterReading).where(
            FuelPumpMeterReading.tenant_id == auth.tenant_id,
            FuelPumpMeterReading.fuel_pump_id == fuel_pump_id,
            FuelPumpMeterReading.fuel_pump_meter_reading_id.in_((body.start_reading_id, body.end_reading_id)),
        )
    ).all()
    if len(readings) != 2:
        raise AppError("NOT_FOUND")
    by_id = {row.fuel_pump_meter_reading_id: row for row in readings}
    start = by_id[body.start_reading_id]
    end = by_id[body.end_reading_id]
    if (start.measured_at, start.fuel_pump_meter_reading_id) >= (
        end.measured_at,
        end.fuel_pump_meter_reading_id,
    ):
        raise AppError("CONFLICT")
    # Le rapprochement est défini entre deux relevés consécutifs.
    intervening = auth.db.scalar(
        select(FuelPumpMeterReading.fuel_pump_meter_reading_id)
        .where(
            FuelPumpMeterReading.tenant_id == auth.tenant_id,
            FuelPumpMeterReading.fuel_pump_id == fuel_pump_id,
            FuelPumpMeterReading.measured_at > start.measured_at,
            FuelPumpMeterReading.measured_at < end.measured_at,
        )
        .limit(1)
    )
    if intervening is not None:
        raise AppError("CONFLICT")
    existing = auth.db.scalar(
        select(FuelPumpAnomalyCase).where(
            FuelPumpAnomalyCase.tenant_id == auth.tenant_id,
            FuelPumpAnomalyCase.fuel_pump_id == fuel_pump_id,
            FuelPumpAnomalyCase.start_reading_id == body.start_reading_id,
            FuelPumpAnomalyCase.end_reading_id == body.end_reading_id,
        )
    )
    if existing is not None:
        raise AppError("CONFLICT")
    case = FuelPumpAnomalyCase(
        tenant_id=auth.tenant_id,
        site_id=pump.site_id,
        fuel_pump_id=fuel_pump_id,
        start_reading_id=body.start_reading_id,
        end_reading_id=body.end_reading_id,
        created_by=auth.user_id,
    )
    auth.db.add(case)
    auth.db.flush()
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="fuel.pump.anomaly.open",
        entity_type="fuel",
        entity_id=case.fuel_pump_anomaly_case_id,
        site_id=pump.site_id,
    )
    auth.db.commit()
    return AnomalyCaseOut.model_validate(case, from_attributes=True)


@router.get("/fuel/anomaly-cases", response_model=Page[AnomalyCaseOut])
def list_anomaly_cases(
    auth: Read, page: Pagination, site_id: uuid.UUID | None = None
) -> Page[AnomalyCaseOut]:
    if site_id is not None and not auth.scope.covers_site(site_id):
        raise AppError("NOT_FOUND")
    condition = [FuelPumpAnomalyCase.tenant_id == auth.tenant_id]
    if not auth.scope.tenant_wide:
        condition.append(FuelPumpAnomalyCase.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        condition.append(FuelPumpAnomalyCase.site_id == site_id)
    count = auth.db.scalar(select(func.count()).select_from(FuelPumpAnomalyCase).where(*condition)) or 0
    cases = auth.db.scalars(
        select(FuelPumpAnomalyCase)
        .where(*condition)
        .order_by(FuelPumpAnomalyCase.created_at.desc())
        .offset(page.offset)
        .limit(page.page_size)
    ).all()
    return Page(
        items=[AnomalyCaseOut.model_validate(c, from_attributes=True) for c in cases],
        total=count,
        page=page.page,
        page_size=page.page_size,
    )


@router.post(
    "/fuel/anomaly-cases/{fuel_pump_anomaly_case_id}/events",
    response_model=AnomalyEventOut,
    status_code=status.HTTP_201_CREATED,
)
def record_anomaly_event(
    fuel_pump_anomaly_case_id: uuid.UUID, body: AnomalyEventCreate, auth: Manage
) -> AnomalyEventOut:
    case = _case(auth, fuel_pump_anomaly_case_id, lock=True)
    last = auth.db.scalar(
        select(FuelPumpAnomalyEvent)
        .where(
            FuelPumpAnomalyEvent.tenant_id == auth.tenant_id,
            FuelPumpAnomalyEvent.fuel_pump_anomaly_case_id == case.fuel_pump_anomaly_case_id,
        )
        .order_by(
            FuelPumpAnomalyEvent.occurred_at.desc(), FuelPumpAnomalyEvent.fuel_pump_anomaly_event_id.desc()
        )
        .limit(1)
    )
    current = last.event_type if last else None
    allowed = {
        None: {"ACKNOWLEDGED"},
        "ACKNOWLEDGED": {"JUSTIFIED"},
        "JUSTIFIED": {"CLOSED"},
        "CLOSED": set(),
    }
    if body.event_type not in allowed[current]:
        raise AppError("CONFLICT")
    if body.event_type == "CLOSED" and case.created_by == auth.user_id:
        raise AppError("CONFLICT")
    event = FuelPumpAnomalyEvent(
        tenant_id=auth.tenant_id,
        fuel_pump_anomaly_case_id=case.fuel_pump_anomaly_case_id,
        event_type=body.event_type,
        justification=body.justification,
        actor_user_id=auth.user_id,
    )
    auth.db.add(event)
    auth.db.flush()
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="fuel.pump.anomaly.event",
        entity_type="fuel",
        entity_id=case.fuel_pump_anomaly_case_id,
        site_id=case.site_id,
    )
    auth.db.commit()
    return AnomalyEventOut.model_validate(event, from_attributes=True)


@router.get("/fuel/anomaly-cases/{fuel_pump_anomaly_case_id}/events", response_model=Page[AnomalyEventOut])
def list_anomaly_events(
    fuel_pump_anomaly_case_id: uuid.UUID, auth: Read, page: Pagination
) -> Page[AnomalyEventOut]:
    case = _case(auth, fuel_pump_anomaly_case_id)
    condition = (
        FuelPumpAnomalyEvent.tenant_id == auth.tenant_id,
        FuelPumpAnomalyEvent.fuel_pump_anomaly_case_id == case.fuel_pump_anomaly_case_id,
    )
    total = auth.db.scalar(select(func.count()).select_from(FuelPumpAnomalyEvent).where(*condition)) or 0
    rows = auth.db.scalars(
        select(FuelPumpAnomalyEvent)
        .where(*condition)
        .order_by(FuelPumpAnomalyEvent.occurred_at)
        .offset(page.offset)
        .limit(page.page_size)
    ).all()
    return Page(
        items=[AnomalyEventOut.model_validate(e, from_attributes=True) for e in rows],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )
