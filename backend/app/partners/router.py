import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import AwareDatetime, BaseModel

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.http import IfMatch, etag
from app.fleet.contracts import vehicle_subcontractors
from app.maintenance.reliability import VehicleReliability
from app.maintenance.reliability import reliability as reliability_report
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
PerformanceRead = Annotated[Authorized, Depends(Require("partner.performance.read"))]
HUNDRED = Decimal(100)
CENT = Decimal("0.01")


class SubcontractorPerformance(BaseModel):
    subcontractor_id: uuid.UUID
    code: str
    legal_name: str
    status: str
    availability_target_percent: Decimal | None
    vehicles: int
    service_hours: Decimal
    downtime_hours: Decimal
    availability_percent: Decimal | None
    # None : aucun objectif SLA saisi, ou aucun engin mesuré sur la période.
    sla_met: bool | None
    failures: int
    mtbf_hours: Decimal | None
    mttr_hours: Decimal | None
    operating_hours: Decimal | None
    measured_tonnes: Decimal | None
    tonnes_per_operating_hour: Decimal | None
    tonnage_pending: bool


class PerformanceOut(BaseModel):
    period_start: datetime
    period_end: datetime
    tonnage_visible: bool
    subcontractors: list[SubcontractorPerformance]


def _aggregate(partner: Subcontractor, rows: list[VehicleReliability]) -> SubcontractorPerformance:
    service = sum((r.service_hours for r in rows), Decimal("0"))
    downtime = sum((r.downtime_hours for r in rows), Decimal("0"))
    failures = sum(r.failures for r in rows)
    availability = ((service - downtime) * HUNDRED / service).quantize(CENT) if service else None
    repaired = [r for r in rows if r.mttr_hours is not None and r.closed_corrective]
    repairs = sum(r.closed_corrective for r in repaired)
    mttr = (
        (
            sum((r.mttr_hours * r.closed_corrective for r in repaired if r.mttr_hours), Decimal("0"))
            / repairs
        ).quantize(CENT)
        if repairs
        else None
    )
    metered = [r for r in rows if r.operating_hours is not None and not r.meter_anomaly]
    operating = (
        sum((r.operating_hours for r in metered if r.operating_hours), Decimal("0")) if metered else None
    )
    weighed = [r for r in metered if r.measured_tonnes is not None]
    tonnes = sum((r.measured_tonnes for r in weighed if r.measured_tonnes), Decimal("0")) if weighed else None
    weighed_hours = sum((r.operating_hours for r in weighed if r.operating_hours), Decimal("0"))
    target = partner.availability_target_percent
    return SubcontractorPerformance(
        subcontractor_id=partner.subcontractor_id,
        code=partner.code,
        legal_name=partner.legal_name,
        status=partner.status,
        availability_target_percent=target,
        vehicles=len(rows),
        service_hours=service,
        downtime_hours=downtime,
        availability_percent=availability,
        sla_met=None if target is None or availability is None else availability >= target,
        failures=failures,
        mtbf_hours=((service - downtime) / failures).quantize(CENT) if failures else None,
        mttr_hours=mttr,
        operating_hours=operating,
        measured_tonnes=tonnes,
        tonnes_per_operating_hour=(tonnes / weighed_hours).quantize(CENT)
        if tonnes is not None and weighed_hours
        else None,
        tonnage_pending=any(r.tonnage_pending for r in rows),
    )


def _out(subcontractor: Subcontractor, response: Response | None = None) -> SubcontractorOut:
    if response is not None:
        response.headers["ETag"] = etag(subcontractor.row_version)
    return SubcontractorOut.model_validate(subcontractor, from_attributes=True)


@router.get("/subcontractors", response_model=list[SubcontractorOut])
def list_subcontractors(
    auth: SubcontractorRead, status: SubcontractorStatus | None = None
) -> list[SubcontractorOut]:
    return [_out(s) for s in service.list_subcontractors(auth, status=status)]


@router.get("/subcontractors/performance", response_model=PerformanceOut)
def subcontractor_performance(
    auth: PerformanceRead,
    period_start: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    period_end: Annotated[AwareDatetime | None, Query(alias="to")] = None,
) -> PerformanceOut:
    """Performance mesurée par sous-traitant, à partir des engins rattachés (tranche 3).

    Réutilise le calcul de fiabilité (durée de service, immobilisation, horamètre, tonnage mesuré) dans la
    portée de l'appelant ; le tonnage reste soumis à `dispatch.indicators.read`. Aucune valeur déclarée par un
    tiers.
    """
    report = reliability_report(auth, site_id=None, period_start=period_start, period_end=period_end)
    links = vehicle_subcontractors(auth.db, [r.vehicle_id for r in report.vehicles])
    by_partner: dict[uuid.UUID, list[VehicleReliability]] = {}
    for row in report.vehicles:
        partner_id = links.get(row.vehicle_id)
        if partner_id is not None:
            by_partner.setdefault(partner_id, []).append(row)
    return PerformanceOut(
        period_start=report.period_start,
        period_end=report.period_end,
        tonnage_visible=report.tonnage_visible,
        subcontractors=[
            _aggregate(partner, by_partner.get(partner.subcontractor_id, []))
            for partner in service.list_subcontractors(auth)
        ],
    )


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
