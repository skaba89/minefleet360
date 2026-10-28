"""Relevés de compteur et documents réglementaires des véhicules (lot 2c, docs/PLAN_LOT2.md §8).

- Relevés en AJOUT SEUL, ordonnés et en progression plausible ; une baisse n'est admise qu'avec une
  remise à zéro motivée (RM-101 à RM-103). Les relevés d'un véhicule sont sérialisés par son verrou.
- Documents : jamais supprimés, retirés avec motif ; validité dérivée des dates au fuseau du site (D-03).
  Les documents bloquants conditionnent l'affectation via le contrat fleet (RM-104).
"""

import uuid
from datetime import UTC, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.http import PageParams, check_version
from app.core.logging import security_logger
from app.core.validity import derive_validity
from app.fleet.models import Vehicle, VehicleCategory, VehicleDocument, VehicleMeterReading
from app.fleet.schemas import (
    BLOCKING_BY_DEFAULT,
    DocumentCreate,
    DocumentOut,
    DocumentUpdate,
    MeterReadingCreate,
    MeterReadingOut,
)
from app.organization.contracts import site_timezone


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


def _reading_out(r: VehicleMeterReading) -> MeterReadingOut:
    return MeterReadingOut(
        vehicle_meter_reading_id=r.vehicle_meter_reading_id,
        vehicle_id=r.vehicle_id,
        meter_kind=r.meter_kind,
        value=float(r.value),
        read_at=r.read_at,
        source=r.source,
        reset_reason=r.reset_reason,
        recorded_by=r.recorded_by,
        recorded_at=r.recorded_at,
    )


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
    return [_reading_out(r) for r in rows], total


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


def _plausible(kind: str, delta: Decimal, elapsed: timedelta) -> bool:
    """RM-103 : une progression physiquement possible sur le temps écoulé."""
    hours = Decimal(elapsed.total_seconds()) / Decimal(3600)
    if kind == "HOUR_METER":
        return delta <= hours * Decimal("1.05") + Decimal("0.1")
    return delta <= hours * get_settings().meter_max_kmh + Decimal(1)


def record_reading(auth: Authorized, vehicle_id: uuid.UUID, body: MeterReadingCreate) -> MeterReadingOut:
    """US-2.09 : relevé ordonné, en progression plausible, ou remise à zéro motivée."""
    settings = get_settings()
    db = auth.db
    vehicle = _vehicle(auth, vehicle_id, lock=True)
    if vehicle.status == "RETIRED":
        raise AppError("STATE_TRANSITION_INVALID", details={"status": vehicle.status})
    category = db.get(VehicleCategory, vehicle.vehicle_category_id)
    equipped = category is not None and (
        category.has_odometer if body.meter_kind == "ODOMETER_KM" else category.has_hour_meter
    )
    if not equipped:
        raise AppError("VALIDATION_ERROR", details=[{"field": "meter_kind", "type": "not_on_category"}])
    now = auth.clock.now()
    at = body.read_at.astimezone(UTC) if body.read_at else now
    if at > now + settings.clock_skew_tolerance or at < now - settings.meter_backdate_tolerance:
        raise AppError("VALIDATION_ERROR", details=[{"field": "read_at", "type": "out_of_tolerance"}])
    last = _last_reading(auth, vehicle_id, body.meter_kind)
    if last is not None:
        if at < last.read_at:
            raise AppError("VALIDATION_ERROR", details=[{"field": "read_at", "type": "before_last_reading"}])
        if body.reset_reason is None:
            delta = body.value - last.value
            if delta < 0:
                raise AppError("VALIDATION_ERROR", details=[{"field": "value", "type": "below_last_reading"}])
            if not _plausible(body.meter_kind, delta, at - last.read_at):
                raise AppError(
                    "VALIDATION_ERROR", details=[{"field": "value", "type": "implausible_increase"}]
                )
    reading = VehicleMeterReading(
        tenant_id=auth.tenant_id,
        vehicle_id=vehicle.vehicle_id,
        site_id=vehicle.site_id,
        meter_kind=body.meter_kind,
        value=body.value,
        read_at=at,
        reset_reason=body.reset_reason,
        recorded_by=auth.user_id,
    )
    db.add(reading)
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="vehicle_meter.record",
        entity_type="vehicle",
        entity_id=vehicle.vehicle_id,
        site_id=vehicle.site_id,
        actor_user_id=auth.user_id,
        reason=body.reset_reason,
        before={"value": float(last.value)} if last is not None else None,
        after={"meter_kind": body.meter_kind, "value": float(body.value), "read_at": at.isoformat()},
    )
    out = _reading_out(reading)
    db.commit()
    return out


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
    zones = {site: site_timezone(db, site) for site in {v.site_id for v in vehicles.values()}}
    now = auth.clock.now()
    warning_days = get_settings().expiry_warning_days
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
                blocks_assignment=d.blocks_assignment,
                validity=derive_validity(
                    stored_status=d.status,
                    valid_from=d.valid_from,
                    valid_until=d.valid_until,
                    now=now,
                    tz=zones[vehicle.site_id],
                    warning_days=warning_days,
                ),
                row_version=d.row_version,
            )
        )
    return out


def list_documents(auth: Authorized, vehicle_id: uuid.UUID) -> list[DocumentOut]:
    _vehicle(auth, vehicle_id)
    docs = auth.db.execute(
        select(VehicleDocument)
        .where(VehicleDocument.vehicle_id == vehicle_id)
        .order_by(VehicleDocument.doc_type, VehicleDocument.valid_until.desc().nulls_last())
    ).scalars()
    return documents_out(auth, list(docs))


def due_documents(auth: Authorized, *, site_id: uuid.UUID | None, within_days: int) -> list[DocumentOut]:
    """Documents en vigueur échus ou arrivant à échéance (alerte de conformité), bornés en volume."""
    horizon = auth.clock.now().date() + timedelta(days=within_days + 1)
    stmt = (
        select(VehicleDocument)
        .join(Vehicle, Vehicle.vehicle_id == VehicleDocument.vehicle_id)
        .where(
            VehicleDocument.status == "VALID",
            VehicleDocument.valid_until.is_not(None),
            VehicleDocument.valid_until <= horizon,
            Vehicle.status != "RETIRED",
        )
    )
    if not auth.scope.tenant_wide:
        stmt = stmt.where(Vehicle.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        stmt = stmt.where(Vehicle.site_id == site_id)
    docs = list(auth.db.execute(stmt.order_by(VehicleDocument.valid_until).limit(500)).scalars())
    # Remplacé par un exemplaire plus récent et valide du même type : n'est plus une alerte.
    return [
        d
        for d in documents_out(auth, docs)
        if d.validity in ("EXPIRING", "EXPIRED") and not _renewed(auth, d)
    ]


def _renewed(auth: Authorized, doc: DocumentOut) -> bool:
    later = auth.db.execute(
        select(func.count()).where(
            VehicleDocument.vehicle_id == doc.vehicle_id,
            VehicleDocument.doc_type == doc.doc_type,
            VehicleDocument.status == "VALID",
            VehicleDocument.vehicle_document_id != doc.vehicle_document_id,
            VehicleDocument.valid_until > doc.valid_until,
        )
    ).scalar_one()
    return bool(later)


def _document(auth: Authorized, document_id: uuid.UUID) -> tuple[VehicleDocument, Vehicle]:
    found = auth.db.execute(
        select(VehicleDocument, Vehicle)
        .join(Vehicle, Vehicle.vehicle_id == VehicleDocument.vehicle_id)
        .where(VehicleDocument.vehicle_document_id == document_id)
    ).one_or_none()
    if found is None or not auth.scope.covers_site(found[1].site_id):
        security_logger.info(
            "item_not_found", extra={"entity_type": "vehicle_document", "entity_id": str(document_id)}
        )
        raise AppError("NOT_FOUND")
    document = auth.db.execute(
        select(VehicleDocument)
        .where(VehicleDocument.vehicle_document_id == document_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    ).scalar_one()
    return document, found[1]


def _check_document(doc_from: Any, doc_until: Any, blocks: bool) -> None:
    if doc_from is not None and doc_until is not None and doc_until < doc_from:
        raise AppError("END_BEFORE_START")
    if blocks and doc_until is None:
        # Un document bloquant sans échéance ne bloquerait jamais (RM-104).
        raise AppError(
            "VALIDATION_ERROR", details=[{"field": "valid_until", "type": "required_when_blocking"}]
        )


def _snapshot(d: VehicleDocument) -> dict[str, Any]:
    return {
        "doc_type": d.doc_type,
        "reference": d.reference,
        "valid_from": d.valid_from.isoformat() if d.valid_from else None,
        "valid_until": d.valid_until.isoformat() if d.valid_until else None,
        "blocks_assignment": d.blocks_assignment,
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
    """US-2.10 : document réglementaire, bloquant ou non pour l'affectation (C-06)."""
    db = auth.db
    vehicle = _vehicle(auth, vehicle_id, lock=True)
    if vehicle.status == "RETIRED":
        raise AppError("STATE_TRANSITION_INVALID", details={"status": vehicle.status})
    blocks = (
        body.blocks_assignment if body.blocks_assignment is not None else body.doc_type in BLOCKING_BY_DEFAULT
    )
    _check_document(body.valid_from, body.valid_until, blocks)
    document = VehicleDocument(
        tenant_id=auth.tenant_id,
        vehicle_id=vehicle.vehicle_id,
        doc_type=body.doc_type,
        reference=body.reference.strip(),
        issuer=body.issuer,
        valid_from=body.valid_from,
        valid_until=body.valid_until,
        blocks_assignment=blocks,
        created_by=auth.user_id,
        updated_by=auth.user_id,
    )
    db.add(document)
    db.flush()
    _audit(auth, "vehicle_document.create", document, vehicle.site_id, after=_snapshot(document))
    out = documents_out(auth, [document])[0]
    db.commit()
    return out


def update_document(
    auth: Authorized, document_id: uuid.UUID, body: DocumentUpdate, version: int
) -> DocumentOut:
    db = auth.db
    document, vehicle = _document(auth, document_id)
    check_version(version, document.row_version)
    if document.status != "VALID":
        raise AppError("STATE_TRANSITION_INVALID", details={"status": document.status})
    fields = tuple(sorted(f for f in body.model_fields_set if getattr(body, f) is not None))
    before = _snapshot(document)
    for name in fields:
        setattr(document, name, getattr(body, name))
    _check_document(document.valid_from, document.valid_until, document.blocks_assignment)
    document.updated_by = auth.user_id
    db.flush()
    _audit(
        auth,
        "vehicle_document.update",
        document,
        vehicle.site_id,
        before=before,
        after=_snapshot(document),
        changed_fields=fields,
    )
    out = documents_out(auth, [document])[0]
    db.commit()
    return out


def withdraw_document(auth: Authorized, document_id: uuid.UUID, reason: str, version: int) -> DocumentOut:
    """RM-105 : un document n'est jamais supprimé ; il est retiré avec un motif codé."""
    db = auth.db
    document, vehicle = _document(auth, document_id)
    check_version(version, document.row_version)
    if document.status != "VALID":
        raise AppError("STATE_TRANSITION_INVALID", details={"status": document.status})
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
