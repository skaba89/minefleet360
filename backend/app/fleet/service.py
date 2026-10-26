"""Services flotte : catégories (lecture), véhicules, machine à états du statut (D-02, RM-014/015)."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.assignment.contracts import open_assignments
from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.authz.principal import mask
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.http import PageParams, check_version
from app.core.logging import security_logger
from app.fleet.models import Vehicle, VehicleCategory, VehicleCategoryLicense, VehicleStatusHistory
from app.fleet.schemas import (
    StatusHistoryOut,
    VehicleCategoryOut,
    VehicleCreate,
    VehicleRetire,
    VehicleStatusChange,
    VehicleUpdate,
)
from app.organization.contracts import local_date, site_in_scope

# Transitions manuelles autorisées (MODELE_CONCEPTUEL 4.1) ; RETIRED passe par la réforme (US-1.15).
TRANSITIONS: dict[str, frozenset[str]] = {
    "AVAILABLE": frozenset({"IN_MAINTENANCE", "IMMOBILIZED", "OUT_OF_SERVICE"}),
    "IMMOBILIZED": frozenset({"IN_MAINTENANCE", "AVAILABLE", "OUT_OF_SERVICE"}),
    "IN_MAINTENANCE": frozenset({"AVAILABLE", "IMMOBILIZED", "OUT_OF_SERVICE"}),
    "OUT_OF_SERVICE": frozenset({"IN_MAINTENANCE"}),
    "RETIRED": frozenset(),
}
REASON_REQUIRED = frozenset({"IMMOBILIZED", "OUT_OF_SERVICE", "RETIRED"})
_TRACKED = (
    "site_id",
    "vehicle_category_id",
    "fleet_number",
    "registration_number",
    "serial_number",
    "make",
    "model",
    "model_year",
    "ownership_type",
    "fuel_type",
    "rated_payload_kg",
    "status",
    "status_reason_code",
    "commissioned_on",
    "decommissioned_on",
)


def _snapshot(vehicle: Vehicle, fields: tuple[str, ...] = _TRACKED) -> dict[str, Any]:
    """Valeurs journalisées : jamais le texte libre `notes` (seul son nom dans changed_fields, SEC1B-04)."""
    return {name: getattr(vehicle, name) for name in fields if name != "notes"}


def _jsonable(data: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in data.items()}


def _ensure_no_open_assignments(db: Session, vehicle_id: uuid.UUID) -> None:
    """Affectations ouvertes bloquant un changement de statut ou de site (D-11, D-13)."""
    blockers = open_assignments(db, vehicle_id=vehicle_id)
    if blockers:
        limit = get_settings().blocking_list_max
        raise AppError("OPEN_ASSIGNMENTS_EXIST", details={"total": len(blockers), "items": blockers[:limit]})


# --- Catégories ---------------------------------------------------------------------------------------


def _category_out(db: Session, categories: list[VehicleCategory]) -> list[VehicleCategoryOut]:
    ids = [c.vehicle_category_id for c in categories]
    licenses: dict[uuid.UUID, list[str]] = {i: [] for i in ids}
    rows = db.execute(
        select(VehicleCategoryLicense.vehicle_category_id, VehicleCategoryLicense.license_category_code)
        .where(VehicleCategoryLicense.vehicle_category_id.in_(ids))
        .order_by(VehicleCategoryLicense.license_category_code)
    )
    for category_id, code in rows:
        licenses[category_id].append(code)
    return [
        VehicleCategoryOut(
            vehicle_category_id=c.vehicle_category_id,
            code=c.code,
            label_fr=c.label_fr,
            family=c.family,
            requires_driver=c.requires_driver,
            requires_internal_authorization=c.requires_internal_authorization,
            has_odometer=c.has_odometer,
            has_hour_meter=c.has_hour_meter,
            is_active=c.is_active,
            required_license_categories=licenses[c.vehicle_category_id],
        )
        for c in categories
    ]


def list_categories(auth: Authorized) -> list[VehicleCategoryOut]:
    rows = auth.db.execute(select(VehicleCategory).order_by(VehicleCategory.family, VehicleCategory.code))
    return _category_out(auth.db, list(rows.scalars()))


def get_category(auth: Authorized, category_id: uuid.UUID) -> VehicleCategoryOut:
    category = auth.db.get(VehicleCategory, category_id)
    if category is None:
        raise AppError("NOT_FOUND")
    return _category_out(auth.db, [category])[0]


def _active_category(db: Session, category_id: uuid.UUID) -> VehicleCategory:
    category = db.get(VehicleCategory, category_id)
    if category is None or not category.is_active:
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "vehicle_category_id"}])
    return category


# --- Véhicules ----------------------------------------------------------------------------------------


def _vehicle_in_scope(auth: Authorized, vehicle_id: uuid.UUID, *, for_update: bool = False) -> Vehicle:
    stmt = select(Vehicle).where(Vehicle.vehicle_id == vehicle_id)
    if for_update:
        stmt = stmt.with_for_update(key_share=True)
    vehicle = auth.db.execute(stmt).scalar_one_or_none()
    if vehicle is None or not auth.scope.covers_site(vehicle.site_id):
        security_logger.info("item_not_found", extra={"entity_type": "vehicle", "entity_id": str(vehicle_id)})
        raise AppError("NOT_FOUND")
    return vehicle


def list_vehicles(
    auth: Authorized,
    page: PageParams,
    *,
    site_id: uuid.UUID | None,
    category_id: uuid.UUID | None,
    status: str | None,
    registration: str | None,
    fleet_number: str | None,
    include_retired: bool,
) -> tuple[list[Vehicle], int]:
    stmt = select(Vehicle)
    if not auth.scope.tenant_wide:
        stmt = stmt.where(Vehicle.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        stmt = stmt.where(Vehicle.site_id == site_id)
    if category_id is not None:
        stmt = stmt.where(Vehicle.vehicle_category_id == category_id)
    if status is not None:
        stmt = stmt.where(Vehicle.status == status)
    elif not include_retired:
        stmt = stmt.where(Vehicle.status != "RETIRED")  # US-1.15 A1 : réformés hors listes par défaut
    if registration:
        normalized = "".join(ch for ch in registration.upper() if ch not in " -")
        stmt = stmt.where(Vehicle.registration_norm == normalized)
    if fleet_number:
        stmt = stmt.where(Vehicle.fleet_number_norm == fleet_number.strip().lower())
    total = auth.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = auth.db.execute(
        stmt.order_by(Vehicle.fleet_number_norm, Vehicle.vehicle_id).offset(page.offset).limit(page.page_size)
    )
    return list(rows.scalars()), total


def get_vehicle(auth: Authorized, vehicle_id: uuid.UUID) -> Vehicle:
    return _vehicle_in_scope(auth, vehicle_id)


def status_history(auth: Authorized, vehicle_id: uuid.UUID) -> list[StatusHistoryOut]:
    vehicle = _vehicle_in_scope(auth, vehicle_id)
    rows = auth.db.execute(
        select(VehicleStatusHistory)
        .where(VehicleStatusHistory.vehicle_id == vehicle_id)
        .order_by(VehicleStatusHistory.changed_at.desc(), VehicleStatusHistory.vehicle_status_history_id)
    )
    return [
        StatusHistoryOut(
            **mask(
                "vehicle_status_history",
                auth.scope,
                {
                    "from_status": h.from_status,
                    "to_status": h.to_status,
                    "reason_code": h.reason_code,
                    "changed_at": h.changed_at,
                    "changed_by": h.changed_by,
                },
                vehicle.site_id,
            )
        )
        for h in rows.scalars()
    ]


def create_vehicle(auth: Authorized, body: VehicleCreate) -> Vehicle:
    """US-1.12 : site et catégorie doivent appartenir au tenant ET à la portée (422 sinon)."""
    db = auth.db
    if site_in_scope(db, auth.scope, body.site_id) is None:
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "site_id"}])
    _active_category(db, body.vehicle_category_id)
    vehicle = Vehicle(
        tenant_id=auth.tenant_id,
        **body.model_dump(),
        status="AVAILABLE",
        created_by=auth.user_id,
        updated_by=auth.user_id,
    )
    db.add(vehicle)
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="vehicle.create",
        entity_type="vehicle",
        entity_id=vehicle.vehicle_id,
        site_id=vehicle.site_id,
        actor_user_id=auth.user_id,
        after=_jsonable(_snapshot(vehicle)),
    )
    db.commit()
    return vehicle


def update_vehicle(
    auth: Authorized, vehicle_id: uuid.UUID, body: VehicleUpdate, expected_version: int
) -> Vehicle:
    db = auth.db
    vehicle = _vehicle_in_scope(auth, vehicle_id, for_update=True)
    check_version(expected_version, vehicle.row_version)
    if vehicle.status == "RETIRED":
        raise AppError(
            "VEHICLE_STATUS_TRANSITION_INVALID", message_fr="Un véhicule réformé n'est plus modifiable."
        )
    fields = tuple(sorted(body.model_fields_set))
    for required in ("site_id", "vehicle_category_id", "ownership_type"):
        if required in fields and getattr(body, required) is None:
            raise AppError("VALIDATION_ERROR", details=[{"field": required, "type": "missing"}])
    if body.site_id is not None and body.site_id != vehicle.site_id:
        if site_in_scope(db, auth.scope, body.site_id) is None:
            raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "site_id"}])
        _ensure_no_open_assignments(db, vehicle.vehicle_id)  # D-13
    if body.vehicle_category_id is not None and body.vehicle_category_id != vehicle.vehicle_category_id:
        _active_category(db, body.vehicle_category_id)
    before = _snapshot(vehicle, fields)
    for name in fields:
        setattr(vehicle, name, getattr(body, name))
    vehicle.updated_by = auth.user_id
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="vehicle.update",
        entity_type="vehicle",
        entity_id=vehicle.vehicle_id,
        site_id=vehicle.site_id,
        actor_user_id=auth.user_id,
        before=_jsonable(before),
        after=_jsonable(_snapshot(vehicle, fields)),
        changed_fields=fields,
    )
    db.commit()
    return vehicle


def _apply_status(
    auth: Authorized, vehicle: Vehicle, target: str, reason: str | None, action: str
) -> Vehicle:
    db = auth.db
    source = vehicle.status
    if target in REASON_REQUIRED and reason is None:
        raise AppError("STATUS_REASON_REQUIRED")
    if target != "AVAILABLE":
        _ensure_no_open_assignments(db, vehicle.vehicle_id)  # D-11
    # Calculé AVANT toute mutation : la requête déclencherait un autoflush partiel (ck_vehicle_retired).
    decommissioned = local_date(db, vehicle.site_id, auth.clock.now()) if target == "RETIRED" else None
    vehicle.status = target
    vehicle.status_reason_code = reason if target != "AVAILABLE" else None
    if decommissioned is not None:
        vehicle.decommissioned_on = decommissioned
    vehicle.updated_by = auth.user_id
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action=action,
        entity_type="vehicle",
        entity_id=vehicle.vehicle_id,
        site_id=vehicle.site_id,
        actor_user_id=auth.user_id,
        reason=reason,
        before={"status": source},
        after={"status": target, "status_reason_code": vehicle.status_reason_code},
        changed_fields=("status", "status_reason_code"),
    )
    db.commit()
    return vehicle


def change_status(
    auth: Authorized, vehicle_id: uuid.UUID, body: VehicleStatusChange, expected_version: int
) -> Vehicle:
    """US-1.14 : transitions de la machine à états ; RETIRED est terminal (C-13)."""
    vehicle = _vehicle_in_scope(auth, vehicle_id, for_update=True)
    check_version(expected_version, vehicle.row_version)
    if body.status not in TRANSITIONS[vehicle.status]:
        raise AppError(
            "VEHICLE_STATUS_TRANSITION_INVALID",
            details={
                "from": vehicle.status,
                "to": body.status,
                "allowed": sorted(TRANSITIONS[vehicle.status]),
            },
        )
    return _apply_status(auth, vehicle, body.status, body.reason_code, "vehicle.change_status")


def retire_vehicle(
    auth: Authorized, vehicle_id: uuid.UUID, body: VehicleRetire, expected_version: int
) -> Vehicle:
    """US-1.15 : réforme depuis tout statut non terminal (D-34 : pas de circuit d'approbation au lot 1)."""
    vehicle = _vehicle_in_scope(auth, vehicle_id, for_update=True)
    check_version(expected_version, vehicle.row_version)
    if vehicle.status == "RETIRED":
        raise AppError("VEHICLE_STATUS_TRANSITION_INVALID", details={"from": "RETIRED", "to": "RETIRED"})
    return _apply_status(auth, vehicle, "RETIRED", body.reason_code, "vehicle.retire")
