"""Relevés de compteur, documents réglementaires et documents exigés (lot 2c, docs/PLAN_LOT2.md §8).

- Relevés en AJOUT SEUL, ordonnés et en progression plausible (plafond par catégorie, D-43). Une baisse
  n'est possible que par une REMISE À ZÉRO, action distincte réservée à l'atelier et à l'exploitation.
- Documents immuables une fois saisis (trigger) : seul le retrait motivé est possible ; une erreur se
  corrige par retrait puis nouvel exemplaire. Validité dérivée des dates au fuseau du site (D-03).
- L'exigence vient de la catégorie du véhicule (D-42) : elle ne peut pas être contournée document par
  document. Les verrous suivent l'ordre des affectations : véhicule puis document.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import aliased

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.authz.principal import mask
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.http import PageParams, check_version
from app.core.logging import security_logger
from app.core.validity import derive_validity
from app.fleet.contracts import required_documents
from app.fleet.models import (
    Vehicle,
    VehicleCategory,
    VehicleCategoryDocument,
    VehicleDocument,
    VehicleMeterReading,
)
from app.fleet.schemas import (
    UNDATED_TYPES,
    CategoryDocumentsOut,
    DocumentCreate,
    DocumentOut,
    MeterReadingCreate,
    MeterReadingOut,
    MeterReset,
    VehicleDocumentsOut,
)
from app.organization.contracts import site_timezone

# D-43 : vitesse moyenne maximale plausible entre deux relevés, par catégorie du catalogue (km/h).
# Engins et tombereaux de site : 60 ; camions routiers, citernes, porte-engins : 100 ; légers, bus : 130.
MAX_KMH_BY_CATEGORY: dict[str, int] = {
    "ARTICULATED_DUMP_TRUCK": 60,
    "RIGID_DUMP_TRUCK": 60,
    "HYDRAULIC_EXCAVATOR": 60,
    "WHEEL_LOADER": 60,
    "BULLDOZER": 60,
    "MOTOR_GRADER": 60,
    "COMPACTOR": 60,
    "FORKLIFT_TELEHANDLER": 60,
    "ROAD_DUMP_TRUCK": 100,
    "FUEL_TANKER": 100,
    "WATER_TANKER": 100,
    "LOWBED_TRAILER": 100,
    "LIGHT_VEHICLE": 130,
    "PERSONNEL_BUS": 130,
}


def _vehicle(auth: Authorized, vehicle_id: uuid.UUID, *, lock: bool = False) -> Vehicle:
    stmt = select(Vehicle).where(Vehicle.vehicle_id == vehicle_id)
    vehicle = auth.db.execute(stmt).scalar_one_or_none()
    if vehicle is None or not auth.scope.covers_site(vehicle.site_id):
        security_logger.info("item_not_found", extra={"entity_type": "vehicle", "entity_id": str(vehicle_id)})
        raise AppError("NOT_FOUND")
    if lock:
        # Verrou APRÈS le contrôle de portée : un véhicule hors portée n'est jamais bloqué.
        auth.db.execute(stmt.with_for_update(key_share=True).execution_options(populate_existing=True))
    return vehicle


# --- Relevés de compteur ------------------------------------------------------------------------------


def _reading_out(auth: Authorized, r: VehicleMeterReading) -> MeterReadingOut:
    data: dict[str, object] = {
        "vehicle_meter_reading_id": r.vehicle_meter_reading_id,
        "vehicle_id": r.vehicle_id,
        "meter_kind": r.meter_kind,
        "value": float(r.value),
        "read_at": r.read_at,
        "source": r.source,
        "reset_reason": r.reset_reason,
        "recorded_by": r.recorded_by,
        "recorded_at": r.recorded_at,
    }
    # Revue L2C-R-08 : l'auteur d'un relevé n'est visible que de l'administration et de l'audit.
    return MeterReadingOut.model_validate(mask("vehicle_meter_reading", auth.scope, data, r.site_id))


def list_readings(
    auth: Authorized, vehicle_id: uuid.UUID, page: PageParams, *, meter_kind: str | None
) -> tuple[list[MeterReadingOut], int]:
    _vehicle(auth, vehicle_id)
    stmt = select(VehicleMeterReading).where(VehicleMeterReading.vehicle_id == vehicle_id)
    if meter_kind is not None:
        stmt = stmt.where(VehicleMeterReading.meter_kind == meter_kind)
    total = auth.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = auth.db.execute(
        stmt.order_by(VehicleMeterReading.read_at.desc(), VehicleMeterReading.recorded_at.desc())
        .offset(page.offset)
        .limit(page.page_size)
    ).scalars()
    return [_reading_out(auth, r) for r in rows], total


def _last_reading(auth: Authorized, vehicle_id: uuid.UUID, kind: str) -> VehicleMeterReading | None:
    return (
        auth.db.execute(
            select(VehicleMeterReading)
            .where(VehicleMeterReading.vehicle_id == vehicle_id, VehicleMeterReading.meter_kind == kind)
            .order_by(VehicleMeterReading.read_at.desc(), VehicleMeterReading.recorded_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def _plausible(kind: str, category: VehicleCategory, delta: Decimal, elapsed: timedelta) -> bool:
    """RM-103 / D-43 : une progression physiquement possible sur le temps écoulé."""
    hours = Decimal(elapsed.total_seconds()) / Decimal(3600)
    if kind == "HOUR_METER":
        return delta <= hours * Decimal("1.05") + Decimal("0.1")
    default = get_settings().meter_max_kmh
    max_kmh = MAX_KMH_BY_CATEGORY.get(category.code, default) if category.is_system else default
    return delta <= hours * max_kmh + Decimal(1)


def _prepare(
    auth: Authorized, vehicle_id: uuid.UUID, kind: str, read_at: datetime | None
) -> tuple[Vehicle, VehicleCategory, datetime, VehicleMeterReading | None]:
    """Contrôles communs au relevé et à la remise à zéro (RM-100, RM-101), sous verrou du véhicule."""
    settings = get_settings()
    vehicle = _vehicle(auth, vehicle_id, lock=True)
    if vehicle.status == "RETIRED":
        raise AppError("STATE_TRANSITION_INVALID", details={"status": vehicle.status})
    category = auth.db.get(VehicleCategory, vehicle.vehicle_category_id)
    assert category is not None
    if not (category.has_odometer if kind == "ODOMETER_KM" else category.has_hour_meter):
        raise AppError("VALIDATION_ERROR", details=[{"field": "meter_kind", "type": "not_on_category"}])
    now = auth.clock.now()
    at = read_at.astimezone(UTC) if read_at else now
    if at > now + settings.clock_skew_tolerance or at < now - settings.meter_backdate_tolerance:
        raise AppError("VALIDATION_ERROR", details=[{"field": "read_at", "type": "out_of_tolerance"}])
    # Revue L2C-R-05 : une avance d'horloge tolérée est ramenée à l'heure serveur, pour ne pas bloquer
    # les relevés suivants.
    at = min(at, now)
    last = _last_reading(auth, vehicle_id, kind)
    if last is not None and at < last.read_at:
        raise AppError("VALIDATION_ERROR", details=[{"field": "read_at", "type": "before_last_reading"}])
    return vehicle, category, at, last


def _save(
    auth: Authorized,
    vehicle: Vehicle,
    kind: str,
    value: Decimal,
    at: datetime,
    last: VehicleMeterReading | None,
    reset_reason: str | None,
) -> MeterReadingOut:
    db = auth.db
    reading = VehicleMeterReading(
        tenant_id=auth.tenant_id,
        vehicle_id=vehicle.vehicle_id,
        site_id=vehicle.site_id,
        meter_kind=kind,
        value=value,
        read_at=at,
        reset_reason=reset_reason,
        recorded_by=auth.user_id,
    )
    db.add(reading)
    db.flush()
    before: dict[str, Any] = {"meter_kind": kind}
    if last is not None:
        before |= {"value": float(last.value), "read_at": last.read_at.isoformat()}
    record(
        db,
        tenant_id=auth.tenant_id,
        action="vehicle_meter.reset" if reset_reason else "vehicle_meter.record",
        entity_type="vehicle",
        entity_id=vehicle.vehicle_id,
        site_id=vehicle.site_id,
        actor_user_id=auth.user_id,
        reason=reset_reason,
        before=before,
        after={
            "vehicle_meter_reading_id": str(reading.vehicle_meter_reading_id),
            "meter_kind": kind,
            "value": float(value),
            "read_at": at.isoformat(),
        },
    )
    out = _reading_out(auth, reading)
    db.commit()
    return out


def record_reading(auth: Authorized, vehicle_id: uuid.UUID, body: MeterReadingCreate) -> MeterReadingOut:
    """US-2.09 : relevé ordonné et en progression plausible ; jamais en baisse (RM-102)."""
    vehicle, category, at, last = _prepare(auth, vehicle_id, body.meter_kind, body.read_at)
    if last is not None:
        delta = body.value - last.value
        if delta < 0:
            raise AppError("VALIDATION_ERROR", details=[{"field": "value", "type": "below_last_reading"}])
        if not _plausible(body.meter_kind, category, delta, at - last.read_at):
            raise AppError("VALIDATION_ERROR", details=[{"field": "value", "type": "implausible_increase"}])
    return _save(auth, vehicle, body.meter_kind, body.value, at, last, None)


def reset_meter(auth: Authorized, vehicle_id: uuid.UUID, body: MeterReset) -> MeterReadingOut:
    """Remise à zéro motivée (revue L2C-R-04) : uniquement vers une valeur INFÉRIEURE au dernier relevé."""
    vehicle, _, at, last = _prepare(auth, vehicle_id, body.meter_kind, body.read_at)
    if last is None or body.value >= last.value:
        raise AppError("VALIDATION_ERROR", details=[{"field": "value", "type": "reset_not_lower"}])
    return _save(auth, vehicle, body.meter_kind, body.value, at, last, body.reset_reason)


# --- Documents ----------------------------------------------------------------------------------------


def documents_out(auth: Authorized, docs: list[VehicleDocument]) -> list[DocumentOut]:
    if not docs:
        return []
    db = auth.db
    vehicles = {
        v.vehicle_id: v
        for v in db.execute(
            select(Vehicle).where(Vehicle.vehicle_id.in_({d.vehicle_id for d in docs}))
        ).scalars()
    }
    required = required_documents(db, {v.vehicle_category_id for v in vehicles.values()})
    zones = {site: site_timezone(db, site) for site in {v.site_id for v in vehicles.values()}}
    now = auth.clock.now()
    warning_days = get_settings().document_warning_days
    out = []
    for d in docs:
        vehicle = vehicles[d.vehicle_id]
        out.append(
            DocumentOut(
                vehicle_document_id=d.vehicle_document_id,
                vehicle_id=d.vehicle_id,
                vehicle_fleet_number=vehicle.fleet_number,
                site_id=vehicle.site_id,
                doc_type=d.doc_type,
                reference=d.reference,
                issuer=d.issuer,
                valid_from=d.valid_from,
                valid_until=d.valid_until,
                status=d.status,
                status_reason=d.status_reason,
                required=d.doc_type in required.get(vehicle.vehicle_category_id, frozenset()),
                validity=derive_validity(
                    stored_status=d.status,
                    valid_from=d.valid_from,
                    valid_until=d.valid_until,
                    now=now,
                    tz=zones[vehicle.site_id],
                    warning_days=warning_days,
                ),
                created_at=d.created_at,
                row_version=d.row_version,
            )
        )
    return out


def list_documents(auth: Authorized, vehicle_id: uuid.UUID) -> VehicleDocumentsOut:
    vehicle = _vehicle(auth, vehicle_id)
    rows = auth.db.execute(
        select(VehicleDocument)
        .where(VehicleDocument.vehicle_id == vehicle_id)
        .order_by(VehicleDocument.doc_type, VehicleDocument.valid_until.desc().nulls_first())
    ).scalars()
    docs = documents_out(auth, list(rows))
    category = vehicle.vehicle_category_id
    required = sorted(required_documents(auth.db, [category]).get(category, ()))
    present = {d.doc_type for d in docs if d.validity in ("VALID", "EXPIRING")}
    return VehicleDocumentsOut(
        documents=docs, required_types=required, missing_types=[t for t in required if t not in present]
    )


def due_documents(auth: Authorized, *, site_id: uuid.UUID | None, within_days: int) -> list[DocumentOut]:
    """Documents en vigueur échus ou arrivant à échéance, non encore renouvelés (revue L2C-R-10)."""
    today = auth.clock.now().date()
    horizon = today + timedelta(days=within_days + 1)
    newer = aliased(VehicleDocument)
    renewed = exists().where(
        newer.vehicle_id == VehicleDocument.vehicle_id,
        newer.doc_type == VehicleDocument.doc_type,
        newer.status == "VALID",
        newer.vehicle_document_id != VehicleDocument.vehicle_document_id,
        or_(newer.valid_until.is_(None), newer.valid_until > horizon),
        or_(newer.valid_from.is_(None), newer.valid_from <= today + timedelta(days=1)),
    )
    stmt = (
        select(VehicleDocument)
        .join(Vehicle, Vehicle.vehicle_id == VehicleDocument.vehicle_id)
        .where(
            VehicleDocument.status == "VALID",
            VehicleDocument.valid_until.is_not(None),
            VehicleDocument.valid_until <= horizon,
            Vehicle.status != "RETIRED",
            ~renewed,
        )
    )
    if not auth.scope.tenant_wide:
        stmt = stmt.where(Vehicle.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        stmt = stmt.where(Vehicle.site_id == site_id)
    docs = list(auth.db.execute(stmt.order_by(VehicleDocument.valid_until).limit(500)).scalars())
    return [d for d in documents_out(auth, docs) if d.validity in ("EXPIRING", "EXPIRED")]


def _snapshot(d: VehicleDocument) -> dict[str, Any]:
    return {
        "doc_type": d.doc_type,
        "reference": d.reference,
        "issuer": d.issuer,
        "valid_from": d.valid_from.isoformat() if d.valid_from else None,
        "valid_until": d.valid_until.isoformat() if d.valid_until else None,
        "status": d.status,
    }


def _audit(auth: Authorized, action: str, d: VehicleDocument, site_id: uuid.UUID, **extra: Any) -> None:
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        action=action,
        entity_type="vehicle_document",
        entity_id=d.vehicle_document_id,
        site_id=site_id,
        actor_user_id=auth.user_id,
        **extra,
    )


def create_document(auth: Authorized, vehicle_id: uuid.UUID, body: DocumentCreate) -> DocumentOut:
    """US-2.10 : nouvel exemplaire d'un document ; un renouvellement est un nouvel exemplaire."""
    db = auth.db
    vehicle = _vehicle(auth, vehicle_id, lock=True)
    if vehicle.status == "RETIRED":
        raise AppError("STATE_TRANSITION_INVALID", details={"status": vehicle.status})
    if body.valid_until is None and body.doc_type not in UNDATED_TYPES:
        raise AppError("VALIDATION_ERROR", details=[{"field": "valid_until", "type": "missing"}])
    if body.valid_from is not None and body.valid_until is not None and body.valid_until < body.valid_from:
        raise AppError("END_BEFORE_START")
    document = VehicleDocument(
        tenant_id=auth.tenant_id,
        vehicle_id=vehicle.vehicle_id,
        doc_type=body.doc_type,
        reference=body.reference.strip(),
        issuer=body.issuer.strip() if body.issuer else None,
        valid_from=body.valid_from,
        valid_until=body.valid_until,
        created_by=auth.user_id,
        updated_by=auth.user_id,
    )
    db.add(document)
    db.flush()
    _audit(auth, "vehicle_document.create", document, vehicle.site_id, after=_snapshot(document))
    out = documents_out(auth, [document])[0]
    db.commit()
    return out


def withdraw_document(auth: Authorized, document_id: uuid.UUID, reason: str, version: int) -> DocumentOut:
    """RM-105 : un document n'est jamais supprimé ni modifié ; il est retiré avec un motif codé."""
    db = auth.db
    vehicle_id = db.execute(
        select(VehicleDocument.vehicle_id).where(VehicleDocument.vehicle_document_id == document_id)
    ).scalar_one_or_none()
    if vehicle_id is None:
        security_logger.info(
            "item_not_found", extra={"entity_type": "vehicle_document", "entity_id": str(document_id)}
        )
        raise AppError("NOT_FOUND")
    # Revue L2C-R-06 : véhicule puis document, dans l'ordre des affectations (portée contrôlée avant).
    vehicle = _vehicle(auth, vehicle_id, lock=True)
    document = db.execute(
        select(VehicleDocument)
        .where(VehicleDocument.vehicle_document_id == document_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    ).scalar_one()
    check_version(version, document.row_version)
    if document.status != "VALID":
        raise AppError("STATE_TRANSITION_INVALID", details={"status": document.status})
    # Revue L2C-R-01 : « erreur de saisie » efface l'exemplaire de l'éligibilité ; seulement peu après la
    # saisie, sinon il servirait à faire disparaître un document échu.
    window = get_settings().document_entry_error_window
    if reason == "ENTRY_ERROR" and auth.clock.now() - document.created_at > window:
        raise AppError("VALIDATION_ERROR", details=[{"field": "reason_code", "type": "entry_error_too_late"}])
    document.status, document.status_reason, document.updated_by = "WITHDRAWN", reason, auth.user_id
    db.flush()
    _audit(
        auth,
        "vehicle_document.withdraw",
        document,
        vehicle.site_id,
        reason=reason,
        before={"status": "VALID"},
        after={"status": "WITHDRAWN"},
        changed_fields=("status",),
    )
    out = documents_out(auth, [document])[0]
    db.commit()
    return out


# --- Documents exigés par catégorie (D-42) --------------------------------------------------------------


def category_documents(auth: Authorized, category_id: uuid.UUID) -> CategoryDocumentsOut:
    category = auth.db.get(VehicleCategory, category_id)
    if category is None:
        raise AppError("NOT_FOUND")
    return CategoryDocumentsOut(
        vehicle_category_id=category_id,
        doc_types=sorted(required_documents(auth.db, [category_id]).get(category_id, ())),
    )


def set_category_documents(
    auth: Authorized, category_id: uuid.UUID, doc_types: list[str]
) -> CategoryDocumentsOut:
    """Remplace la liste des documents exigés d'une catégorie ; effet immédiat sur l'éligibilité."""
    db = auth.db
    category = db.execute(
        select(VehicleCategory).where(VehicleCategory.vehicle_category_id == category_id)
    ).scalar_one_or_none()
    if category is None:
        raise AppError("NOT_FOUND")
    before = sorted(required_documents(db, [category_id]).get(category_id, ()))
    after = sorted(set(doc_types))
    rows = {
        r.doc_type: r
        for r in db.execute(
            select(VehicleCategoryDocument)
            .where(VehicleCategoryDocument.vehicle_category_id == category_id)
            .with_for_update()
        ).scalars()
    }
    for doc_type in sorted(set(after) | set(rows)):
        wanted = doc_type in after
        row = rows.get(doc_type)
        if row is None:
            db.add(
                VehicleCategoryDocument(
                    tenant_id=auth.tenant_id,
                    vehicle_category_id=category_id,
                    doc_type=doc_type,
                    created_by=auth.user_id,
                    updated_by=auth.user_id,
                )
            )
        elif row.required != wanted:
            # Exigence retirée = désactivée, jamais supprimée (D-19).
            row.required, row.updated_by = wanted, auth.user_id
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="vehicle_category.required_documents",
        entity_type="vehicle_category",
        entity_id=category_id,
        actor_user_id=auth.user_id,
        before={"doc_types": before},
        after={"doc_types": after},
        changed_fields=("required_documents",),
    )
    db.commit()
    return CategoryDocumentsOut(vehicle_category_id=category_id, doc_types=after)
