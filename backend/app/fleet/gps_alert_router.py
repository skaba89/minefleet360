"""Alertes GPS : consultation, prise en compte, réglage de la vitesse limite par site (docs/GPS_ALERTS.md).

Les alertes révèlent le comportement de conduite : permissions dédiées, portée site vérifiée, audit de la
prise en compte et des réglages. Les alertes sont produites à l'ingestion (gps_alert_engine), jamais ici.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from app.audit.contracts import record
from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.errors import AppError
from app.core.http import Page, Pagination, StrictModel
from app.fleet.gps_alert_models import GpsAlert, SiteGpsPolicy
from app.fleet.models import Vehicle
from app.organization.models import Site

router = APIRouter(tags=["géolocalisation"], route_class=SecuredRoute)
AlertRead = Annotated[Authorized, Depends(Require("fleet.gps_alert.read"))]
AlertManage = Annotated[Authorized, Depends(Require("fleet.gps_alert.manage"))]
PolicyManage = Annotated[Authorized, Depends(Require("fleet.gps_policy.manage"))]
AlertKind = Literal["OVERSPEED", "RESTRICTED_ZONE_ENTRY", "SITE_BOUNDARY_EXIT"]


class GpsAlertOut(BaseModel):
    gps_alert_id: uuid.UUID
    site_id: uuid.UUID
    vehicle_id: uuid.UUID
    fleet_number: str
    kind: AlertKind
    opened_at: datetime
    last_measured_at: datetime
    closed_at: datetime | None
    latitude: float
    longitude: float
    speed_limit_kmh: Decimal | None
    peak_speed_kmh: float | None
    site_geofence_id: uuid.UUID | None
    geofence_name: str | None
    acknowledged_by: uuid.UUID | None
    acknowledged_at: datetime | None
    acknowledgement_note: str | None


class AcknowledgeIn(StrictModel):
    note: str | None = Field(default=None, max_length=500)


class GpsPolicyOut(BaseModel):
    site_id: uuid.UUID
    speed_limit_kmh: Decimal | None
    updated_at: datetime | None


class GpsPolicyIn(StrictModel):
    speed_limit_kmh: Decimal | None = Field(default=None, gt=0, le=250, max_digits=5, decimal_places=1)


def _site_in_scope(auth: Authorized, site_id: uuid.UUID) -> None:
    exists = auth.db.scalar(
        select(Site.site_id).where(Site.tenant_id == auth.tenant_id, Site.site_id == site_id)
    )
    if exists is None or not auth.scope.covers_site(site_id):
        raise AppError("NOT_FOUND")


def _geofence_names(auth: Authorized, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = auth.db.execute(
        text(
            "SELECT site_geofence_id, name FROM site_geofence "
            "WHERE tenant_id = :t AND site_geofence_id = ANY(:ids)"
        ),
        {"t": auth.tenant_id, "ids": list(ids)},
    ).all()
    return {r.site_geofence_id: r.name for r in rows}


def _out(alert: GpsAlert, fleet_number: str, names: dict[uuid.UUID, str]) -> GpsAlertOut:
    return GpsAlertOut(
        gps_alert_id=alert.gps_alert_id,
        site_id=alert.site_id,
        vehicle_id=alert.vehicle_id,
        fleet_number=fleet_number,
        kind=alert.kind,
        opened_at=alert.opened_at,
        last_measured_at=alert.last_measured_at,
        closed_at=alert.closed_at,
        latitude=alert.latitude,
        longitude=alert.longitude,
        speed_limit_kmh=alert.speed_limit_kmh,
        peak_speed_kmh=alert.peak_speed_kmh,
        site_geofence_id=alert.site_geofence_id,
        geofence_name=names.get(alert.site_geofence_id) if alert.site_geofence_id else None,
        acknowledged_by=alert.acknowledged_by,
        acknowledged_at=alert.acknowledged_at,
        acknowledgement_note=alert.acknowledgement_note,
    )


@router.get("/gps/alerts", response_model=Page[GpsAlertOut])
def list_gps_alerts(
    auth: AlertRead,
    page: Pagination,
    site_id: uuid.UUID | None = None,
    kind: AlertKind | None = None,
    unacknowledged: bool = False,
) -> Page[GpsAlertOut]:
    if site_id is not None:
        _site_in_scope(auth, site_id)
    query = (
        select(GpsAlert, Vehicle.fleet_number)
        .join(
            Vehicle, (Vehicle.tenant_id == GpsAlert.tenant_id) & (Vehicle.vehicle_id == GpsAlert.vehicle_id)
        )
        .where(GpsAlert.tenant_id == auth.tenant_id)
    )
    if site_id is not None:
        query = query.where(GpsAlert.site_id == site_id)
    elif not auth.scope.tenant_wide:
        query = query.where(GpsAlert.site_id.in_(auth.scope.site_ids))
    if kind is not None:
        query = query.where(GpsAlert.kind == kind)
    if unacknowledged:
        query = query.where(GpsAlert.acknowledged_at.is_(None))
    total = auth.db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = auth.db.execute(
        query.order_by(GpsAlert.opened_at.desc(), GpsAlert.gps_alert_id)
        .offset(page.offset)
        .limit(page.page_size)
    ).all()
    names = _geofence_names(auth, {a.site_geofence_id for a, _ in rows if a.site_geofence_id})
    return Page(
        items=[_out(a, fleet, names) for a, fleet in rows],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.post("/gps/alerts/{gps_alert_id}/acknowledge", response_model=GpsAlertOut)
def acknowledge_gps_alert(gps_alert_id: uuid.UUID, body: AcknowledgeIn, auth: AlertManage) -> GpsAlertOut:
    alert = auth.db.scalar(
        select(GpsAlert)
        .where(GpsAlert.tenant_id == auth.tenant_id, GpsAlert.gps_alert_id == gps_alert_id)
        .with_for_update()
    )
    if alert is None or not auth.scope.covers_site(alert.site_id):
        raise AppError("NOT_FOUND")
    if alert.acknowledged_at is not None:
        raise AppError("STATE_TRANSITION_INVALID", message_fr="Cette alerte a déjà été prise en compte.")
    alert.acknowledged_by = auth.user_id
    alert.acknowledged_at = auth.clock.now()
    alert.acknowledgement_note = (body.note or "").strip() or None
    auth.db.flush()
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        site_id=alert.site_id,
        action="fleet.gps.alert.acknowledge",
        entity_type="gps_alert",
        entity_id=alert.gps_alert_id,
        reason=alert.acknowledgement_note,
        changed_fields=("acknowledged_by", "acknowledged_at"),
    )
    auth.db.commit()
    fleet = auth.db.scalar(
        select(Vehicle.fleet_number).where(
            Vehicle.tenant_id == auth.tenant_id, Vehicle.vehicle_id == alert.vehicle_id
        )
    )
    names = _geofence_names(auth, {alert.site_geofence_id} if alert.site_geofence_id else set())
    return _out(alert, fleet or "", names)


@router.get("/sites/{site_id}/gps-policy", response_model=GpsPolicyOut)
def get_gps_policy(site_id: uuid.UUID, auth: AlertRead) -> GpsPolicyOut:
    _site_in_scope(auth, site_id)
    policy = auth.db.scalar(
        select(SiteGpsPolicy).where(
            SiteGpsPolicy.tenant_id == auth.tenant_id, SiteGpsPolicy.site_id == site_id
        )
    )
    return GpsPolicyOut(
        site_id=site_id,
        speed_limit_kmh=policy.speed_limit_kmh if policy else None,
        updated_at=policy.updated_at if policy else None,
    )


@router.put("/sites/{site_id}/gps-policy", response_model=GpsPolicyOut)
def put_gps_policy(site_id: uuid.UUID, body: GpsPolicyIn, auth: PolicyManage) -> GpsPolicyOut:
    _site_in_scope(auth, site_id)
    policy = auth.db.scalar(
        select(SiteGpsPolicy)
        .where(SiteGpsPolicy.tenant_id == auth.tenant_id, SiteGpsPolicy.site_id == site_id)
        .with_for_update()
    )
    before = policy.speed_limit_kmh if policy else None
    now = auth.clock.now()
    if policy is None:
        policy = SiteGpsPolicy(
            tenant_id=auth.tenant_id, site_id=site_id, updated_by=auth.user_id, updated_at=now
        )
        auth.db.add(policy)
    limit = body.speed_limit_kmh.quantize(Decimal("0.1")) if body.speed_limit_kmh is not None else None
    policy.speed_limit_kmh = limit
    policy.updated_by = auth.user_id
    policy.updated_at = now
    auth.db.flush()
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        site_id=site_id,
        action="fleet.gps.policy.update",
        entity_type="site_gps_policy",
        entity_id=site_id,
        before={"speed_limit_kmh": str(before) if before is not None else None},
        after={"speed_limit_kmh": str(limit) if limit is not None else None},
        changed_fields=("speed_limit_kmh",),
    )
    auth.db.commit()
    return GpsPolicyOut(site_id=site_id, speed_limit_kmh=policy.speed_limit_kmh, updated_at=policy.updated_at)
