"""Pneumatiques : cycle de vie, contrôles d'usure, coût au kilomètre et à l'heure (docs/LIVRAISON_PNEUS.md).

- États : IN_STOCK → MOUNTED → IN_STOCK ; IN_STOCK → IN_REPAIR → IN_STOCK (réparé ou rechapé) ; IN_STOCK ou
  IN_REPAIR → SCRAPPED. Chaque étape écrit un événement en ajout seul et un audit, dans la même transaction ;
  concurrence par If-Match et verrou de ligne. Une position ne porte qu'un pneu (index unique partiel).
- Le pneu reste rattaché à un site ; il ne se monte que sur un engin de ce site.
- Coût : achat + réparations + rechapages, dans une seule devise (sinon refus à la saisie).
- Distance et heures : relevés des compteurs de l'engin au montage, aux contrôles et au démontage — aucune
  valeur extrapolée.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.core.http import PageParams, StrictModel, check_version
from app.core.logging import security_logger
from app.fleet.contracts import vehicle_facts
from app.maintenance.models import WorkOrder
from app.maintenance.parts_models import SparePart
from app.maintenance.tyre_models import Tyre, TyreEvent
from app.organization.contracts import active_site_in_scope

Category = Literal["STEER", "DRIVE", "TRAILER", "ALL_POSITION"]
TyreStatus = Literal["IN_STOCK", "MOUNTED", "IN_REPAIR", "SCRAPPED"]
DismountReason = Literal["ROTATION", "WEAR", "DAMAGE", "PUNCTURE", "REPAIR", "VEHICLE_MAINTENANCE", "OTHER"]
RepairAction = Literal["SEND", "REPAIRED", "RETREADED"]
ScrapReason = Literal["WORN_OUT", "IRREPARABLE_DAMAGE", "AGE", "OTHER"]
Alert = Literal["TREAD_AT_LIMIT", "TREAD_LOW", "PRESSURE_DEVIATION", "INSPECTION_OVERDUE"]

POSITION = r"^[A-Z0-9-]{1,16}$"
CURRENCY = r"^[A-Z]{3}$"
TREAD_WARNING_MM = Decimal("3")
PRESSURE_TOLERANCE = Decimal("0.10")
INSPECTION_INTERVAL = timedelta(days=30)


# --- Schémas -------------------------------------------------------------------------------------------


class Meters(StrictModel):
    odometer_km: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999"), decimal_places=1)
    hour_meter: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999"), decimal_places=1)


class TyreCreate(StrictModel):
    site_id: uuid.UUID
    serial_number: str = Field(min_length=1, max_length=64)
    brand: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=64)
    size: str = Field(min_length=1, max_length=32)
    category: Category
    spare_part_id: uuid.UUID | None = None
    purchase_cost: Decimal | None = Field(default=None, ge=0, le=Decimal("1e15"), decimal_places=2)
    currency: str | None = Field(default=None, pattern=CURRENCY)
    initial_tread_mm: Decimal = Field(gt=0, le=300, decimal_places=1)
    scrap_tread_mm: Decimal = Field(ge=0, le=300, decimal_places=1)
    nominal_pressure_kpa: int | None = Field(default=None, ge=1, le=2000)

    @model_validator(mode="after")
    def _consistent(self) -> "TyreCreate":
        if (self.purchase_cost is None) != (self.currency is None):
            raise ValueError("coût d'achat et devise vont ensemble")
        if self.scrap_tread_mm >= self.initial_tread_mm:
            raise ValueError("la limite de rebut doit être inférieure à la sculpture neuve")
        return self


class TyreMount(Meters):
    vehicle_id: uuid.UUID
    position_code: str = Field(pattern=POSITION)
    work_order_id: uuid.UUID | None = None


class TyreDismount(Meters):
    reason_code: DismountReason
    tread_mm: Decimal | None = Field(default=None, ge=0, le=300, decimal_places=1)
    work_order_id: uuid.UUID | None = None


class TyreInspection(Meters):
    tread_mm: Decimal = Field(ge=0, le=300, decimal_places=1)
    pressure_kpa: int | None = Field(default=None, ge=0, le=2000)
    note: str | None = Field(default=None, max_length=1000)


class TyreRepair(StrictModel):
    action: RepairAction
    cost: Decimal | None = Field(default=None, ge=0, le=Decimal("1e15"), decimal_places=2)
    currency: str | None = Field(default=None, pattern=CURRENCY)
    new_tread_mm: Decimal | None = Field(default=None, gt=0, le=300, decimal_places=1)
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _consistent(self) -> "TyreRepair":
        if (self.cost is None) != (self.currency is None):
            raise ValueError("coût et devise vont ensemble")
        if (self.action == "RETREADED") != (self.new_tread_mm is not None):
            raise ValueError(
                "la sculpture après rechapage est exigée pour un rechapage, et seulement pour lui"
            )
        if self.action == "SEND" and self.cost is not None:
            raise ValueError("le coût se saisit au retour de réparation")
        return self


class TyreScrap(StrictModel):
    reason_code: ScrapReason
    tread_mm: Decimal | None = Field(default=None, ge=0, le=300, decimal_places=1)
    note: str | None = Field(default=None, max_length=1000)


class TyreEventOut(BaseModel):
    event_type: str
    vehicle_id: uuid.UUID | None
    position_code: str | None
    odometer_km: Decimal | None
    hour_meter: Decimal | None
    tread_mm: Decimal | None
    pressure_kpa: int | None
    cost: Decimal | None
    currency: str | None
    reason_code: str | None
    work_order_id: uuid.UUID | None
    note: str | None
    occurred_at: datetime


class TyreOut(BaseModel):
    tyre_id: uuid.UUID
    site_id: uuid.UUID
    serial_number: str
    brand: str
    model: str
    size: str
    category: Category
    spare_part_id: uuid.UUID | None
    purchase_cost: Decimal | None
    currency: str | None
    initial_tread_mm: Decimal
    scrap_tread_mm: Decimal
    nominal_pressure_kpa: int | None
    status: TyreStatus
    vehicle_id: uuid.UUID | None
    vehicle_fleet_number: str | None
    spare_part_code: str | None
    position_code: str | None
    mounted_at: datetime | None
    retread_count: int
    last_tread_mm: Decimal | None
    last_pressure_kpa: int | None
    last_inspected_at: datetime | None
    scrap_reason: str | None
    alerts: list[Alert]
    total_cost: Decimal | None
    cost_complete: bool
    km_run: Decimal
    hours_run: Decimal
    cost_per_km: Decimal | None
    cost_per_hour: Decimal | None
    row_version: int
    events: list[TyreEventOut] | None = None


# --- Calculs purs --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Usage:
    km: Decimal
    hours: Decimal


def usage_from_events(events: list[TyreEvent]) -> Usage:
    """Distance et heures roulées, à partir des relevés de compteurs pendant chaque montage.

    Pour un montage en cours, le dernier relevé connu (contrôle) borne la période : rien n'est extrapolé.
    """
    km = Decimal("0")
    hours = Decimal("0")
    start: dict[str, Decimal | None] = {"km": None, "h": None}
    last: dict[str, Decimal | None] = {"km": None, "h": None}

    def close() -> None:
        nonlocal km, hours
        if start["km"] is not None and last["km"] is not None and last["km"] > start["km"]:
            km += last["km"] - start["km"]
        if start["h"] is not None and last["h"] is not None and last["h"] > start["h"]:
            hours += last["h"] - start["h"]

    mounted = False
    for e in events:
        if e.event_type == "MOUNTED":
            mounted = True
            start = {"km": e.odometer_km, "h": e.hour_meter}
            last = dict(start)
        elif mounted and e.event_type in ("INSPECTED", "DISMOUNTED"):
            if e.odometer_km is not None:
                last["km"] = e.odometer_km
            if e.hour_meter is not None:
                last["h"] = e.hour_meter
            if e.event_type == "DISMOUNTED":
                close()
                mounted = False
    if mounted:
        close()
    return Usage(km=km, hours=hours)


def alerts_for(tyre: Tyre, now: datetime) -> list[Alert]:
    alerts: list[Alert] = []
    if tyre.status == "SCRAPPED":
        return alerts
    tread = tyre.last_tread_mm
    if tread is not None and tread <= tyre.scrap_tread_mm:
        alerts.append("TREAD_AT_LIMIT")
    elif tread is not None and tread <= tyre.scrap_tread_mm + TREAD_WARNING_MM:
        alerts.append("TREAD_LOW")
    if (
        tyre.nominal_pressure_kpa
        and tyre.last_pressure_kpa is not None
        and abs(Decimal(tyre.last_pressure_kpa - tyre.nominal_pressure_kpa)) / tyre.nominal_pressure_kpa
        > PRESSURE_TOLERANCE
    ):
        alerts.append("PRESSURE_DEVIATION")
    if tyre.status == "MOUNTED" and tyre.mounted_at is not None:
        reference = tyre.mounted_at
        if tyre.last_inspected_at is not None and tyre.last_inspected_at > reference:
            reference = tyre.last_inspected_at
        if now - reference > INSPECTION_INTERVAL:
            alerts.append("INSPECTION_OVERDUE")
    return alerts


def _per(total: Decimal | None, quantity: Decimal) -> Decimal | None:
    if total is None or quantity <= 0:
        return None
    return (total / quantity).quantize(Decimal("0.0001"))


# --- Lecture -------------------------------------------------------------------------------------------


def tyres_out(auth: Authorized, tyres: list[Tyre], *, detail: bool = False) -> list[TyreOut]:
    if not tyres:
        return []
    db = auth.db
    ids = [t.tyre_id for t in tyres]
    events: dict[uuid.UUID, list[TyreEvent]] = {i: [] for i in ids}
    for e in db.execute(
        select(TyreEvent)
        .where(TyreEvent.tyre_id.in_(ids))
        .order_by(TyreEvent.occurred_at, TyreEvent.tyre_event_id)
    ).scalars():
        events[e.tyre_id].append(e)
    fleet = vehicle_facts(db, {t.vehicle_id for t in tyres if t.vehicle_id})
    part_ids = {t.spare_part_id for t in tyres if t.spare_part_id}
    parts = (
        dict(
            db.execute(
                select(SparePart.spare_part_id, SparePart.code).where(SparePart.spare_part_id.in_(part_ids))
            ).all()
        )
        if part_ids
        else {}
    )
    now = auth.clock.now()
    out = []
    for t in tyres:
        own = events[t.tyre_id]
        usage = usage_from_events(own)
        extra = [e.cost for e in own if e.cost is not None and e.event_type in ("REPAIRED", "RETREADED")]
        # Coût complet seulement si l'achat est connu ; les saisies sont déjà en devise unique.
        total = (t.purchase_cost + sum(extra, Decimal("0"))) if t.purchase_cost is not None else None
        data: dict[str, Any] = {
            **{
                k: getattr(t, k)
                for k in (
                    "tyre_id",
                    "site_id",
                    "serial_number",
                    "brand",
                    "model",
                    "size",
                    "category",
                    "spare_part_id",
                    "purchase_cost",
                    "currency",
                    "initial_tread_mm",
                    "scrap_tread_mm",
                    "nominal_pressure_kpa",
                    "status",
                    "vehicle_id",
                    "position_code",
                    "mounted_at",
                    "retread_count",
                    "last_tread_mm",
                    "last_pressure_kpa",
                    "last_inspected_at",
                    "scrap_reason",
                    "row_version",
                )
            },
            "vehicle_fleet_number": fleet[t.vehicle_id].fleet_number if t.vehicle_id in fleet else None,
            "spare_part_code": parts.get(t.spare_part_id) if t.spare_part_id else None,
            "alerts": alerts_for(t, now),
            "total_cost": total,
            "cost_complete": total is not None,
            "km_run": usage.km,
            "hours_run": usage.hours,
            "cost_per_km": _per(total, usage.km),
            "cost_per_hour": _per(total, usage.hours),
        }
        if detail:
            data["events"] = [TyreEventOut.model_validate(e, from_attributes=True) for e in own]
        out.append(TyreOut(**data))
    return out


def list_tyres(
    auth: Authorized,
    page: PageParams,
    *,
    site_id: uuid.UUID | None,
    status: str | None,
    vehicle_id: uuid.UUID | None,
    alert_only: bool,
) -> tuple[list[TyreOut], int]:
    if site_id is not None and not auth.scope.covers_site(site_id):
        raise AppError("NOT_FOUND")
    conditions: list[Any] = []
    if not auth.scope.tenant_wide:
        conditions.append(Tyre.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        conditions.append(Tyre.site_id == site_id)
    if status is not None:
        conditions.append(Tyre.status == status)
    if vehicle_id is not None:
        conditions.append(Tyre.vehicle_id == vehicle_id)
    order = (Tyre.brand, Tyre.serial_number)
    if alert_only:
        # Les alertes dépendent de l'heure courante : filtrées en mémoire sur le parc non réformé.
        candidates = db_scalars(auth, [*conditions, Tyre.status != "SCRAPPED"], order)
        now = auth.clock.now()
        flagged = [t for t in candidates if alerts_for(t, now)]
        return tyres_out(auth, flagged[page.offset : page.offset + page.page_size]), len(flagged)
    total = auth.db.execute(select(func.count()).select_from(Tyre).where(*conditions)).scalar_one()
    rows = list(
        auth.db.execute(
            select(Tyre).where(*conditions).order_by(*order).offset(page.offset).limit(page.page_size)
        )
        .scalars()
        .all()
    )
    return tyres_out(auth, rows), int(total)


def db_scalars(auth: Authorized, conditions: list[Any], order: tuple[Any, ...]) -> list[Tyre]:
    return list(auth.db.execute(select(Tyre).where(*conditions).order_by(*order)).scalars().all())


def tyre_in_scope(auth: Authorized, tyre_id: uuid.UUID, *, for_update: bool = False) -> Tyre:
    stmt = select(Tyre).where(Tyre.tyre_id == tyre_id)
    tyre = auth.db.execute(stmt).scalar_one_or_none()
    if tyre is None or not auth.scope.covers_site(tyre.site_id):
        security_logger.info("item_not_found", extra={"entity_type": "tyre", "entity_id": str(tyre_id)})
        raise AppError("NOT_FOUND")
    if for_update:
        tyre = auth.db.execute(stmt.with_for_update().execution_options(populate_existing=True)).scalar_one()
    return tyre


# --- Écriture ------------------------------------------------------------------------------------------


def _event(auth: Authorized, tyre: Tyre, event_type: str, **values: Any) -> None:
    auth.db.add(
        TyreEvent(
            tenant_id=auth.tenant_id,
            tyre_id=tyre.tyre_id,
            event_type=event_type,
            actor_user_id=auth.user_id,
            **values,
        )
    )


def _audit(auth: Authorized, action: str, tyre: Tyre, **extra: Any) -> None:
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        action=action,
        entity_type="tyre",
        entity_id=tyre.tyre_id,
        site_id=tyre.site_id,
        actor_user_id=auth.user_id,
        **extra,
    )


def _done(auth: Authorized, tyre: Tyre) -> TyreOut:
    tyre.updated_by = auth.user_id
    auth.db.flush()
    out = tyres_out(auth, [tyre], detail=True)[0]
    auth.db.commit()
    return out


def _require_meter(meters: Meters) -> None:
    if meters.odometer_km is None and meters.hour_meter is None:
        raise AppError("VALIDATION_ERROR", details=[{"field": "odometer_km", "type": "missing"}])


def _work_order_for(auth: Authorized, work_order_id: uuid.UUID | None, vehicle_id: uuid.UUID) -> None:
    if work_order_id is None:
        return
    order = auth.db.execute(
        select(WorkOrder).where(WorkOrder.work_order_id == work_order_id)
    ).scalar_one_or_none()
    if order is None or order.vehicle_id != vehicle_id:
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "work_order_id"}])


def create_tyre(auth: Authorized, body: TyreCreate) -> TyreOut:
    db = auth.db
    if active_site_in_scope(db, auth.scope, body.site_id) is None:
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "site_id"}])
    if body.spare_part_id is not None:
        part = db.get(SparePart, body.spare_part_id)
        if part is None:
            raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "spare_part_id"}])
        # Article de référence d'un pneu suivi individuellement : compté à l'unité (D-DEL-03).
        if part.unit != "EACH":
            raise AppError("VALIDATION_ERROR", details=[{"field": "spare_part_id", "type": "unit_not_each"}])
    tyre = Tyre(
        tenant_id=auth.tenant_id,
        **body.model_dump(),
        last_tread_mm=body.initial_tread_mm,
        created_by=auth.user_id,
        updated_by=auth.user_id,
    )
    db.add(tyre)
    db.flush()
    _event(auth, tyre, "REGISTERED", tread_mm=body.initial_tread_mm)
    _audit(
        auth,
        "maintenance.tyre.create",
        tyre,
        after={"brand": tyre.brand, "serial_number": tyre.serial_number, "size": tyre.size},
    )
    return _done(auth, tyre)


def mount(auth: Authorized, tyre_id: uuid.UUID, body: TyreMount, version: int) -> TyreOut:
    _require_meter(body)
    tyre = tyre_in_scope(auth, tyre_id, for_update=True)
    check_version(version, tyre.row_version)
    if tyre.status != "IN_STOCK":
        raise AppError("TYRE_STATE_INVALID", details={"status": tyre.status, "action": "MOUNT"})
    facts = vehicle_facts(auth.db, [body.vehicle_id], lock=True).get(body.vehicle_id)
    if facts is None or facts.site_id != tyre.site_id or facts.status == "RETIRED":
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "vehicle_id"}])
    _work_order_for(auth, body.work_order_id, body.vehicle_id)
    occupied = auth.db.execute(
        select(Tyre.tyre_id).where(
            Tyre.vehicle_id == body.vehicle_id,
            Tyre.position_code == body.position_code,
            Tyre.status == "MOUNTED",
        )
    ).first()
    if occupied is not None:
        raise AppError("TYRE_POSITION_OCCUPIED")
    tyre.status = "MOUNTED"
    tyre.vehicle_id = body.vehicle_id
    tyre.position_code = body.position_code
    tyre.mounted_at = auth.clock.now()
    _event(
        auth,
        tyre,
        "MOUNTED",
        vehicle_id=body.vehicle_id,
        position_code=body.position_code,
        odometer_km=body.odometer_km,
        hour_meter=body.hour_meter,
        work_order_id=body.work_order_id,
    )
    _audit(
        auth,
        "maintenance.tyre.mount",
        tyre,
        after={"vehicle_id": str(body.vehicle_id), "position_code": body.position_code},
    )
    return _done(auth, tyre)


def _mount_readings(auth: Authorized, tyre: Tyre) -> TyreEvent | None:
    return auth.db.execute(
        select(TyreEvent)
        .where(TyreEvent.tyre_id == tyre.tyre_id, TyreEvent.event_type == "MOUNTED")
        .order_by(TyreEvent.occurred_at.desc(), TyreEvent.tyre_event_id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _check_meters_forward(auth: Authorized, tyre: Tyre, meters: Meters) -> None:
    """Un relevé pendant le montage ne peut pas être inférieur au relevé de montage (compteur de l'engin)."""
    mounted = _mount_readings(auth, tyre)
    if mounted is None:
        return
    for field, start in (("odometer_km", mounted.odometer_km), ("hour_meter", mounted.hour_meter)):
        value = getattr(meters, field)
        if value is not None and start is not None and value < start:
            raise AppError("TYRE_METER_DECREASED", details=[{"field": field}])


def dismount(auth: Authorized, tyre_id: uuid.UUID, body: TyreDismount, version: int) -> TyreOut:
    _require_meter(body)
    tyre = tyre_in_scope(auth, tyre_id, for_update=True)
    check_version(version, tyre.row_version)
    if tyre.status != "MOUNTED" or tyre.vehicle_id is None:
        raise AppError("TYRE_STATE_INVALID", details={"status": tyre.status, "action": "DISMOUNT"})
    _check_meters_forward(auth, tyre, body)
    _work_order_for(auth, body.work_order_id, tyre.vehicle_id)
    _event(
        auth,
        tyre,
        "DISMOUNTED",
        vehicle_id=tyre.vehicle_id,
        position_code=tyre.position_code,
        odometer_km=body.odometer_km,
        hour_meter=body.hour_meter,
        tread_mm=body.tread_mm,
        reason_code=body.reason_code,
        work_order_id=body.work_order_id,
    )
    before = {"vehicle_id": str(tyre.vehicle_id), "position_code": tyre.position_code}
    tyre.status = "IN_STOCK"
    tyre.vehicle_id = None
    tyre.position_code = None
    tyre.mounted_at = None
    if body.tread_mm is not None:
        tyre.last_tread_mm = body.tread_mm
    _audit(auth, "maintenance.tyre.dismount", tyre, reason=body.reason_code, before=before)
    return _done(auth, tyre)


def inspect(auth: Authorized, tyre_id: uuid.UUID, body: TyreInspection, version: int) -> TyreOut:
    tyre = tyre_in_scope(auth, tyre_id, for_update=True)
    check_version(version, tyre.row_version)
    if tyre.status not in ("IN_STOCK", "MOUNTED"):
        raise AppError("TYRE_STATE_INVALID", details={"status": tyre.status, "action": "INSPECT"})
    if tyre.status == "MOUNTED":
        _check_meters_forward(auth, tyre, body)
    now = auth.clock.now()
    _event(
        auth,
        tyre,
        "INSPECTED",
        vehicle_id=tyre.vehicle_id,
        position_code=tyre.position_code,
        odometer_km=body.odometer_km if tyre.status == "MOUNTED" else None,
        hour_meter=body.hour_meter if tyre.status == "MOUNTED" else None,
        tread_mm=body.tread_mm,
        pressure_kpa=body.pressure_kpa,
        note=body.note or None,
    )
    tyre.last_tread_mm = body.tread_mm
    tyre.last_pressure_kpa = body.pressure_kpa
    tyre.last_inspected_at = now
    _audit(auth, "maintenance.tyre.inspect", tyre, changed_fields=["last_tread_mm", "last_pressure_kpa"])
    return _done(auth, tyre)


def repair(auth: Authorized, tyre_id: uuid.UUID, body: TyreRepair, version: int) -> TyreOut:
    tyre = tyre_in_scope(auth, tyre_id, for_update=True)
    check_version(version, tyre.row_version)
    if body.currency is not None and tyre.currency is not None and body.currency != tyre.currency:
        raise AppError("TYRE_CURRENCY_MISMATCH", details=[{"field": "currency"}])
    if body.cost is not None and tyre.currency is None:
        # Sans coût d'achat la devise du pneu n'est pas fixée : on refuse d'agréger des montants hétérogènes.
        raise AppError("TYRE_CURRENCY_MISMATCH", details=[{"field": "currency"}])
    if body.action == "SEND":
        if tyre.status != "IN_STOCK":
            raise AppError("TYRE_STATE_INVALID", details={"status": tyre.status, "action": body.action})
        tyre.status = "IN_REPAIR"
        _event(auth, tyre, "SENT_TO_REPAIR", note=body.note or None)
    else:
        if tyre.status != "IN_REPAIR":
            raise AppError("TYRE_STATE_INVALID", details={"status": tyre.status, "action": body.action})
        tyre.status = "IN_STOCK"
        if body.action == "RETREADED":
            if tyre.retread_count >= 20:
                raise AppError("TYRE_STATE_INVALID", details={"status": tyre.status, "action": body.action})
            tyre.retread_count += 1
            tyre.last_tread_mm = body.new_tread_mm
        _event(
            auth,
            tyre,
            body.action,
            cost=body.cost,
            currency=body.currency,
            tread_mm=body.new_tread_mm,
            note=body.note or None,
        )
    _audit(
        auth,
        f"maintenance.tyre.{body.action.lower()}",
        tyre,
        after={"status": tyre.status, "cost": str(body.cost) if body.cost is not None else None},
    )
    return _done(auth, tyre)


def scrap(auth: Authorized, tyre_id: uuid.UUID, body: TyreScrap, version: int) -> TyreOut:
    tyre = tyre_in_scope(auth, tyre_id, for_update=True)
    check_version(version, tyre.row_version)
    if tyre.status not in ("IN_STOCK", "IN_REPAIR"):
        raise AppError("TYRE_STATE_INVALID", details={"status": tyre.status, "action": "SCRAP"})
    tyre.status = "SCRAPPED"
    tyre.scrap_reason = body.reason_code
    if body.tread_mm is not None:
        tyre.last_tread_mm = body.tread_mm
    _event(
        auth, tyre, "SCRAPPED", reason_code=body.reason_code, tread_mm=body.tread_mm, note=body.note or None
    )
    _audit(auth, "maintenance.tyre.scrap", tyre, reason=body.reason_code)
    return _done(auth, tyre)


class TyreStockRow(BaseModel):
    site_id: uuid.UUID
    size: str
    brand: str
    model: str
    spare_part_code: str | None
    in_stock: int
    mounted: int
    in_repair: int
    alerts_in_stock: int


def stock_summary(auth: Authorized, site_id: uuid.UUID | None) -> list[TyreStockRow]:
    """Stock de pneus (D-DEL-03) : le registre individuel fait foi ; les pneus au rebut sont exclus."""
    if site_id is not None and not auth.scope.covers_site(site_id):
        raise AppError("NOT_FOUND")
    conditions: list[Any] = [Tyre.status != "SCRAPPED"]
    if not auth.scope.tenant_wide:
        conditions.append(Tyre.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        conditions.append(Tyre.site_id == site_id)
    tyres = db_scalars(auth, conditions, (Tyre.size, Tyre.brand, Tyre.model))
    codes = {
        pid: code
        for pid, code in auth.db.execute(
            select(SparePart.spare_part_id, SparePart.code).where(
                SparePart.spare_part_id.in_({t.spare_part_id for t in tyres if t.spare_part_id})
            )
        ).all()
    }
    now = auth.clock.now()
    rows: dict[tuple[uuid.UUID, str, str, str, str | None], dict[str, int]] = {}
    for t in tyres:
        key = (t.site_id, t.size, t.brand, t.model, codes.get(t.spare_part_id) if t.spare_part_id else None)
        row = rows.setdefault(key, {"in_stock": 0, "mounted": 0, "in_repair": 0, "alerts_in_stock": 0})
        column = {"IN_STOCK": "in_stock", "MOUNTED": "mounted", "IN_REPAIR": "in_repair"}[t.status]
        row[column] += 1
        if t.status == "IN_STOCK" and alerts_for(t, now):
            row["alerts_in_stock"] += 1
    return [
        TyreStockRow(site_id=k[0], size=k[1], brand=k[2], model=k[3], spare_part_code=k[4], **v)
        for k, v in sorted(
            rows.items(), key=lambda item: (str(item[0][0]), item[0][1], item[0][2], item[0][3])
        )
    ]
