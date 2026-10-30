"""Traitement des dossiers d'anomalie carburant, strictement limité au tenant et au site."""

import uuid
from decimal import Decimal
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from app.audit.contracts import record
from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.errors import AppError
from app.core.http import Page, Pagination, StrictModel
from app.fuel import service
from app.fuel.models import FuelPump, FuelPumpAnomalyCase, FuelPumpAnomalyEvent, FuelPumpMeterReading

router = APIRouter(tags=["carburant"], route_class=SecuredRoute)
Read = Annotated[Authorized, Depends(Require("fuel.anomaly.read"))]
Manage = Annotated[Authorized, Depends(Require("fuel.anomaly.manage"))]
EventType = Literal["ACKNOWLEDGED", "JUSTIFIED", "CLOSED"]
AnomalyStatus = Literal["OPEN", "ACKNOWLEDGED", "JUSTIFIED", "CLOSED"]
QualificationReason = Literal[
    "LEGACY_UNQUALIFIED",
    "METER_VOLUME_EXCEEDS_APPROVED_ISSUES",
    "APPROVED_ISSUES_EXCEED_METER_VOLUME",
]


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
    meter_delta_liters: Decimal | None
    approved_issue_liters: Decimal | None
    variance_liters: Decimal | None
    variance_percent: Decimal | None
    tolerance_liters: Decimal | None
    tolerance_percent: Decimal | None
    qualification_reason: QualificationReason
    created_by: uuid.UUID
    status: AnomalyStatus


class AnomalyEventOut(BaseModel):
    fuel_pump_anomaly_event_id: uuid.UUID
    fuel_pump_anomaly_case_id: uuid.UUID
    event_type: EventType
    justification: str
    actor_user_id: uuid.UUID


def _case_output(case: FuelPumpAnomalyCase, current_status: AnomalyStatus) -> AnomalyCaseOut:
    return AnomalyCaseOut(
        fuel_pump_anomaly_case_id=case.fuel_pump_anomaly_case_id,
        fuel_pump_id=case.fuel_pump_id,
        site_id=case.site_id,
        start_reading_id=case.start_reading_id,
        end_reading_id=case.end_reading_id,
        meter_delta_liters=case.meter_delta_liters,
        approved_issue_liters=case.approved_issue_liters,
        variance_liters=case.variance_liters,
        variance_percent=case.variance_percent,
        tolerance_liters=case.tolerance_liters,
        tolerance_percent=case.tolerance_percent,
        qualification_reason=cast(QualificationReason, case.qualification_reason),
        created_by=case.created_by,
        status=current_status,
    )


def _case(auth: Authorized, case_id: uuid.UUID) -> FuelPumpAnomalyCase:
    query = select(FuelPumpAnomalyCase).where(
        FuelPumpAnomalyCase.tenant_id == auth.tenant_id,
        FuelPumpAnomalyCase.fuel_pump_anomaly_case_id == case_id,
    )
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
    pump_query = select(FuelPump).where(
        FuelPump.tenant_id == auth.tenant_id,
        FuelPump.fuel_pump_id == fuel_pump_id,
    )
    if not auth.scope.tenant_wide:
        pump_query = pump_query.where(FuelPump.site_id.in_(auth.scope.site_ids))
    pump = auth.db.scalar(pump_query.with_for_update())
    if pump is None:
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
    reconciliation = service.reconcile_pump_interval(auth, pump, start, end)
    if reconciliation["is_anomaly"] is not True:
        raise AppError(
            "FUEL_INTERVAL_NOT_ANOMALOUS",
            details={
                "variance_liters": str(reconciliation["variance_liters"]),
                "variance_percent": str(reconciliation["variance_percent"]),
                "tolerance_liters": str(reconciliation["tolerance_liters"]),
                "tolerance_percent": str(reconciliation["tolerance_percent"]),
            },
        )
    variance_liters = cast(Decimal, reconciliation["variance_liters"])
    qualification_reason: QualificationReason = (
        "METER_VOLUME_EXCEEDS_APPROVED_ISSUES"
        if variance_liters > 0
        else "APPROVED_ISSUES_EXCEED_METER_VOLUME"
    )
    case = FuelPumpAnomalyCase(
        tenant_id=auth.tenant_id,
        site_id=pump.site_id,
        fuel_pump_id=fuel_pump_id,
        start_reading_id=body.start_reading_id,
        end_reading_id=body.end_reading_id,
        meter_delta_liters=cast(Decimal, reconciliation["meter_delta_liters"]),
        approved_issue_liters=cast(Decimal, reconciliation["approved_issue_liters"]),
        variance_liters=variance_liters,
        variance_percent=cast(Decimal, reconciliation["variance_percent"]),
        tolerance_liters=cast(Decimal, reconciliation["tolerance_liters"]),
        tolerance_percent=cast(Decimal, reconciliation["tolerance_percent"]),
        qualification_reason=qualification_reason,
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
        reason=qualification_reason,
        changed_fields=("qualification_snapshot",),
    )
    output = _case_output(case, "OPEN")
    auth.db.commit()
    return output


@router.get("/fuel/anomaly-cases", response_model=Page[AnomalyCaseOut])
def list_anomaly_cases(
    auth: Read,
    page: Pagination,
    site_id: uuid.UUID | None = None,
    status_filter: Annotated[AnomalyStatus | None, Query(alias="status")] = None,
) -> Page[AnomalyCaseOut]:
    if site_id is not None and not auth.scope.covers_site(site_id):
        raise AppError("NOT_FOUND")
    condition = [FuelPumpAnomalyCase.tenant_id == auth.tenant_id]
    if not auth.scope.tenant_wide:
        condition.append(FuelPumpAnomalyCase.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        condition.append(FuelPumpAnomalyCase.site_id == site_id)
    latest_status = (
        select(FuelPumpAnomalyEvent.event_type)
        .where(
            FuelPumpAnomalyEvent.tenant_id == FuelPumpAnomalyCase.tenant_id,
            FuelPumpAnomalyEvent.fuel_pump_anomaly_case_id == FuelPumpAnomalyCase.fuel_pump_anomaly_case_id,
        )
        .order_by(
            FuelPumpAnomalyEvent.occurred_at.desc(),
            FuelPumpAnomalyEvent.fuel_pump_anomaly_event_id.desc(),
        )
        .limit(1)
        .correlate(FuelPumpAnomalyCase)
        .scalar_subquery()
    )
    current_status = func.coalesce(latest_status, "OPEN").label("current_status")
    query = select(FuelPumpAnomalyCase, current_status).where(*condition)
    if status_filter is not None:
        query = query.where(current_status == status_filter)
    count = auth.db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = auth.db.execute(
        query.order_by(FuelPumpAnomalyCase.created_at.desc()).offset(page.offset).limit(page.page_size)
    ).all()
    return Page(
        items=[_case_output(case, cast(AnomalyStatus, row_status)) for case, row_status in rows],
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
    case = _case(auth, fuel_pump_anomaly_case_id)
    # Verrou transactionnel sans UPDATE sur la table append-only.
    auth.db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:case_id, 0))"),
        {"case_id": str(case.fuel_pump_anomaly_case_id)},
    )
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
