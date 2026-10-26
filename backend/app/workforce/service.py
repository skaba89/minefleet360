"""Services personnel : conducteurs, permis, habilitations, échéances (US-1.16 à US-1.21).

Portée : un conducteur est rattaché à un site ; permis et habilitations héritent de la portée du conducteur.
Données personnelles : masquage serveur selon field_policies (D-15) ; jamais de valeur sensible dans l'audit.
"""

import unicodedata
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select

from app.assignment.contracts import ensure_no_open_assignments
from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.authz.principal import mask, restricted_fields
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.http import PageParams, check_version
from app.core.logging import security_logger
from app.organization.contracts import active_site_in_scope, site_in_scope, site_timezone
from app.workforce.models import Driver, DriverLicense, DriverQualification
from app.workforce.schemas import (
    DriverCreate,
    DriverOut,
    DriverStatusChange,
    DriverUpdate,
    ExpirationItem,
    LicenseCreate,
    LicenseOut,
    LicenseUpdate,
    QualificationCreate,
    QualificationOut,
    QualificationRevoke,
)
from app.workforce.validity import ELIGIBLE, derive_validity

# Dérivé de field_policies (source unique) : aucune valeur restreinte dans l'audit (revue 1b).
SENSITIVE_DRIVER_FIELDS = restricted_fields("driver")
# Seuls champs dont la VALEUR est journalisée : opérationnels, non nominatifs (SEC1B-02, D-10).
AUDIT_VALUED_DRIVER_FIELDS = frozenset({"site_id", "status", "unavailability_reason", "unavailable_until"})
assert not AUDIT_VALUED_DRIVER_FIELDS & SENSITIVE_DRIVER_FIELDS


def _norm_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).lower().split())


def _jsonable(data: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in data.items()}


def _ensure_no_open_assignments(auth: Authorized, driver: Driver) -> None:
    """Affectations ouvertes du conducteur bloquant un changement de statut ou de site (D-11, D-13)."""
    ensure_no_open_assignments(auth.db, auth.principal, driver.site_id, driver_id=driver.driver_id)


# --- Sérialisation ------------------------------------------------------------------------------------


def _authorized_categories(auth: Authorized, drivers: list[Driver]) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Catégories d'engins pour lesquelles l'habilitation de conduite est éligible aujourd'hui."""
    result: dict[uuid.UUID, list[uuid.UUID]] = {d.driver_id: [] for d in drivers}
    if not drivers:
        return result
    site_of = {d.driver_id: d.site_id for d in drivers}
    rows = auth.db.execute(
        select(DriverQualification).where(
            DriverQualification.driver_id.in_(list(result)),
            DriverQualification.qualification_type == "DRIVING_AUTHORIZATION",
            DriverQualification.status == "VALID",
        )
    ).scalars()
    now, warning = auth.clock.now(), get_settings().expiry_warning_days
    zones: dict[uuid.UUID, Any] = {}
    for q in rows:
        site = site_of[q.driver_id]
        tz = zones.setdefault(site, site_timezone(auth.db, site))
        validity = derive_validity(
            stored_status=q.status,
            valid_from=q.valid_from,
            valid_until=q.valid_to,
            now=now,
            tz=tz,
            warning_days=warning,
        )
        if validity in ELIGIBLE and q.vehicle_category_id is not None:
            result[q.driver_id].append(q.vehicle_category_id)
    return result


def driver_out(
    auth: Authorized, driver: Driver, categories: list[uuid.UUID], warnings: list[str] | None = None
) -> DriverOut:
    data: dict[str, Any] = {
        "driver_id": driver.driver_id,
        "site_id": driver.site_id,
        "employee_number": driver.employee_number,
        "last_name": driver.last_name,
        "first_name": driver.first_name,
        "status": driver.status,
        "unavailability_reason": driver.unavailability_reason,
        "unavailable_until": driver.unavailable_until,
        "authorized_category_ids": categories,
        "phone": driver.phone,
        "suspension_reason_code": driver.suspension_reason_code,
        "employment_type": driver.employment_type,
        "external_company_name": driver.external_company_name,
        "hire_date": driver.hire_date,
        "exit_date": driver.exit_date,
        "created_at": driver.created_at,
        "row_version": driver.row_version,
    }
    if warnings:
        data["warnings"] = warnings
    return DriverOut(**mask("driver", auth.scope, data, driver.site_id))


def drivers_out(auth: Authorized, drivers: list[Driver]) -> list[DriverOut]:
    categories = _authorized_categories(auth, drivers)
    return [driver_out(auth, d, categories[d.driver_id]) for d in drivers]


def _license_out(auth: Authorized, lic: DriverLicense, site_id: uuid.UUID) -> LicenseOut:
    validity = derive_validity(
        stored_status=lic.status,
        valid_from=lic.issue_date,
        valid_until=lic.expiry_date,
        now=auth.clock.now(),
        tz=site_timezone(auth.db, site_id),
        warning_days=get_settings().expiry_warning_days,
    )
    data: dict[str, Any] = {
        "driver_license_id": lic.driver_license_id,
        "driver_id": lic.driver_id,
        "category_code": lic.category_code,
        "issue_date": lic.issue_date,
        "expiry_date": lic.expiry_date,
        "status": lic.status,
        "validity": validity,
        "issuing_authority": lic.issuing_authority,
        "license_number": lic.license_number,
        "document_reference": lic.document_reference,
        "status_note": lic.status_note,
        "row_version": lic.row_version,
    }
    return LicenseOut(**mask("driver_license", auth.scope, data, site_id))


def _qualification_out(auth: Authorized, q: DriverQualification, site_id: uuid.UUID) -> QualificationOut:
    validity = derive_validity(
        stored_status=q.status,
        valid_from=q.valid_from,
        valid_until=q.valid_to,
        now=auth.clock.now(),
        tz=site_timezone(auth.db, site_id),
        warning_days=get_settings().expiry_warning_days,
    )
    data: dict[str, Any] = {
        "driver_qualification_id": q.driver_qualification_id,
        "driver_id": q.driver_id,
        "qualification_type": q.qualification_type,
        "vehicle_category_id": q.vehicle_category_id,
        "site_id": q.site_id,
        "valid_from": q.valid_from,
        "valid_to": q.valid_to,
        "status": q.status,
        "validity": validity,
        "issued_by_name": q.issued_by_name,
        "reference": q.reference,
        "restrictions": q.restrictions,
        "row_version": q.row_version,
    }
    # Texte libre (risque de donnée médicale) : HR/HSE seulement (SEC1B-03).
    return QualificationOut(**mask("driver_qualification", auth.scope, data, site_id))


# --- Conducteurs --------------------------------------------------------------------------------------


def driver_in_scope(auth: Authorized, driver_id: uuid.UUID, *, for_update: bool = False) -> Driver:
    stmt = select(Driver).where(Driver.driver_id == driver_id)
    if for_update:
        stmt = stmt.with_for_update(key_share=True)
    driver = auth.db.execute(stmt).scalar_one_or_none()
    if driver is None or not auth.scope.covers_site(driver.site_id):
        security_logger.info("item_not_found", extra={"entity_type": "driver", "entity_id": str(driver_id)})
        raise AppError("NOT_FOUND")
    return driver


def list_drivers(
    auth: Authorized, page: PageParams, *, site_id: uuid.UUID | None, status: str | None, search: str | None
) -> tuple[list[Driver], int]:
    stmt = select(Driver)
    if not auth.scope.tenant_wide:
        stmt = stmt.where(Driver.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        stmt = stmt.where(Driver.site_id == site_id)
    if status is not None:
        stmt = stmt.where(Driver.status == status)
    if search:
        pattern = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            func.lower(Driver.last_name).like(pattern)
            | func.lower(Driver.first_name).like(pattern)
            | func.lower(Driver.employee_number).like(pattern)
        )
    total = auth.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = auth.db.execute(
        stmt.order_by(func.lower(Driver.last_name), func.lower(Driver.first_name), Driver.driver_id)
        .offset(page.offset)
        .limit(page.page_size)
    )
    return list(rows.scalars()), total


def create_driver(auth: Authorized, body: DriverCreate) -> tuple[Driver, list[str]]:
    """US-1.16 : matricule unique (409) ; homonyme sur le même site = avertissement non bloquant (A6)."""
    db = auth.db
    if active_site_in_scope(db, auth.scope, body.site_id) is None:
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "site_id"}])
    if body.employment_type == "SUBCONTRACTOR" and not body.external_company_name:
        raise AppError("VALIDATION_ERROR", details=[{"field": "external_company_name", "type": "missing"}])
    target = (_norm_name(body.last_name), _norm_name(body.first_name))
    same_site = db.execute(
        select(Driver.last_name, Driver.first_name).where(Driver.site_id == body.site_id)
    ).all()
    warnings = (
        ["POSSIBLE_DUPLICATE"]
        if any((_norm_name(r[0]), _norm_name(r[1])) == target for r in same_site)
        else []
    )
    driver = Driver(
        tenant_id=auth.tenant_id, **body.model_dump(), created_by=auth.user_id, updated_by=auth.user_id
    )
    db.add(driver)
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="driver.create",
        entity_type="driver",
        entity_id=driver.driver_id,
        site_id=driver.site_id,
        actor_user_id=auth.user_id,
        # Ni nom ni matricule : le journal est lisible par TENANT_ADMIN, qui ne lit pas les personnes (D-10).
        after={"site_id": str(driver.site_id), "status": driver.status},
        changed_fields=sorted(body.model_fields_set),
    )
    db.commit()
    return driver, warnings


def update_driver(
    auth: Authorized, driver_id: uuid.UUID, body: DriverUpdate, expected_version: int
) -> DriverOut:
    db = auth.db
    driver = driver_in_scope(auth, driver_id, for_update=True)
    check_version(expected_version, driver.row_version)
    fields = tuple(sorted(body.model_fields_set))
    for required in ("site_id", "last_name", "first_name", "employment_type"):
        if required in fields and getattr(body, required) is None:
            raise AppError("VALIDATION_ERROR", details=[{"field": required, "type": "missing"}])
    if body.site_id is not None and body.site_id != driver.site_id:
        if active_site_in_scope(db, auth.scope, body.site_id) is None:
            raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "site_id"}])
        _ensure_no_open_assignments(auth, driver)  # D-13
    visible = tuple(f for f in fields if f in AUDIT_VALUED_DRIVER_FIELDS)
    before = {f: getattr(driver, f) for f in visible}
    for name in fields:
        setattr(driver, name, getattr(body, name))
    driver.updated_by = auth.user_id
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="driver.update",
        entity_type="driver",
        entity_id=driver.driver_id,
        site_id=driver.site_id,
        actor_user_id=auth.user_id,
        before=_jsonable(before),
        after=_jsonable({f: getattr(driver, f) for f in visible}),
        changed_fields=fields,
    )
    out = drivers_out(auth, [driver])[0]  # avant COMMIT : le contexte tenant (SET LOCAL) disparaît après
    db.commit()
    return out


def change_driver_status(
    auth: Authorized, driver_id: uuid.UUID, body: DriverStatusChange, expected_version: int
) -> DriverOut:
    """US-1.21 : motif obligatoire selon le statut ; refus 409 si affectations ouvertes (D-11)."""
    db = auth.db
    driver = driver_in_scope(auth, driver_id, for_update=True)
    check_version(expected_version, driver.row_version)
    target, source = body.status, driver.status
    if target == source:
        raise AppError("STATE_TRANSITION_INVALID")
    required = {
        "UNAVAILABLE": body.unavailability_reason,
        "SUSPENDED": body.suspension_reason_code,
        "INACTIVE": body.exit_date,
    }
    if target in required and required[target] is None:
        raise AppError("STATUS_REASON_REQUIRED")
    if target != "ACTIVE":
        _ensure_no_open_assignments(auth, driver)
    if target != "INACTIVE" and active_site_in_scope(db, auth.scope, driver.site_id) is None:
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "site_id"}])
    driver.status = target
    driver.unavailability_reason = body.unavailability_reason if target == "UNAVAILABLE" else None
    driver.unavailable_until = body.unavailable_until if target == "UNAVAILABLE" else None
    driver.suspension_reason_code = body.suspension_reason_code if target == "SUSPENDED" else None
    driver.exit_date = body.exit_date if target == "INACTIVE" else None
    if driver.exit_date and driver.hire_date and driver.exit_date < driver.hire_date:
        raise AppError("VALIDATION_ERROR", details=[{"field": "exit_date", "type": "before_hire_date"}])
    driver.updated_by = auth.user_id
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="driver.change_status",
        entity_type="driver",
        entity_id=driver.driver_id,
        site_id=driver.site_id,
        actor_user_id=auth.user_id,
        before={"status": source},
        after={"status": target},
        changed_fields=("status", *(("suspension_reason_code",) if target == "SUSPENDED" else ())),
    )
    out = drivers_out(auth, [driver])[0]  # avant COMMIT : le contexte tenant (SET LOCAL) disparaît après
    db.commit()
    return out


# --- Permis -------------------------------------------------------------------------------------------


def list_licenses(auth: Authorized, driver_id: uuid.UUID) -> list[LicenseOut]:
    driver = driver_in_scope(auth, driver_id)
    rows = auth.db.execute(
        select(DriverLicense)
        .where(DriverLicense.driver_id == driver_id)
        .order_by(DriverLicense.category_code, DriverLicense.expiry_date.desc())
    ).scalars()
    return [_license_out(auth, lic, driver.site_id) for lic in rows]


def create_license(auth: Authorized, driver_id: uuid.UUID, body: LicenseCreate) -> LicenseOut:
    """US-1.18 : un permis par catégorie et délivrance ; le numéro n'apparaît jamais dans l'audit."""
    db = auth.db
    driver = driver_in_scope(auth, driver_id)
    lic = DriverLicense(
        tenant_id=auth.tenant_id,
        driver_id=driver.driver_id,
        **body.model_dump(),
        created_by=auth.user_id,
        updated_by=auth.user_id,
    )
    db.add(lic)
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="driver_license.create",
        entity_type="driver_license",
        entity_id=lic.driver_license_id,
        site_id=driver.site_id,
        actor_user_id=auth.user_id,
        after=_jsonable(
            {
                "driver_id": driver.driver_id,
                "category_code": lic.category_code,
                "issue_date": lic.issue_date,
                "expiry_date": lic.expiry_date,
            }
        ),
        changed_fields=("license_number",),
    )
    out = _license_out(auth, lic, driver.site_id)
    db.commit()
    return out


def _license_in_scope(auth: Authorized, license_id: uuid.UUID) -> tuple[DriverLicense, Driver]:
    lic = auth.db.execute(
        select(DriverLicense)
        .where(DriverLicense.driver_license_id == license_id)
        .with_for_update(key_share=True)
    ).scalar_one_or_none()
    if lic is None:
        raise AppError("NOT_FOUND")
    return lic, driver_in_scope(auth, lic.driver_id)


def update_license(
    auth: Authorized, license_id: uuid.UUID, body: LicenseUpdate, expected_version: int
) -> LicenseOut:
    db = auth.db
    lic, driver = _license_in_scope(auth, license_id)
    check_version(expected_version, lic.row_version)
    fields = tuple(sorted(body.model_fields_set))
    if "status" in fields and body.status is None:
        raise AppError("VALIDATION_ERROR", details=[{"field": "status", "type": "missing"}])
    before = {"status": lic.status}
    for name in fields:
        setattr(lic, name, getattr(body, name))
    lic.updated_by = auth.user_id
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="driver_license.update",
        entity_type="driver_license",
        entity_id=lic.driver_license_id,
        site_id=driver.site_id,
        actor_user_id=auth.user_id,
        before=before,
        after={"status": lic.status},
        changed_fields=fields,
    )
    out = _license_out(auth, lic, driver.site_id)
    db.commit()
    return out


# --- Habilitations ------------------------------------------------------------------------------------


def list_qualifications(auth: Authorized, driver_id: uuid.UUID) -> list[QualificationOut]:
    driver = driver_in_scope(auth, driver_id)
    rows = auth.db.execute(
        select(DriverQualification)
        .where(DriverQualification.driver_id == driver_id)
        .order_by(DriverQualification.valid_from.desc(), DriverQualification.driver_qualification_id)
    ).scalars()
    return [_qualification_out(auth, q, driver.site_id) for q in rows]


def create_qualification(
    auth: Authorized, driver_id: uuid.UUID, body: QualificationCreate
) -> QualificationOut:
    """US-1.19 : catégorie du référentiel du tenant ; chevauchement d'habilitations VALID → 409 (base)."""
    db = auth.db
    driver = driver_in_scope(auth, driver_id)
    if body.site_id is None and not auth.scope.tenant_wide:
        # Une habilitation valable sur tout le tenant exige une portée TENANT (SEC1B-10).
        raise AppError("VALIDATION_ERROR", details=[{"field": "site_id", "type": "required_for_site_scope"}])
    if body.site_id is not None and site_in_scope(db, auth.scope, body.site_id) is None:
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "site_id"}])
    q = DriverQualification(
        tenant_id=auth.tenant_id,
        driver_id=driver.driver_id,
        **body.model_dump(),
        created_by=auth.user_id,
        updated_by=auth.user_id,
    )
    db.add(q)
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="driver_qualification.create",
        entity_type="driver_qualification",
        entity_id=q.driver_qualification_id,
        site_id=driver.site_id,
        actor_user_id=auth.user_id,
        after=_jsonable(
            {
                "driver_id": driver.driver_id,
                "qualification_type": q.qualification_type,
                "vehicle_category_id": q.vehicle_category_id,
                "valid_from": q.valid_from,
                "valid_to": q.valid_to,
            }
        ),
    )
    out = _qualification_out(auth, q, driver.site_id)
    db.commit()
    return out


def revoke_qualification(
    auth: Authorized, qualification_id: uuid.UUID, body: QualificationRevoke, expected_version: int
) -> QualificationOut:
    db = auth.db
    q = db.execute(
        select(DriverQualification)
        .where(DriverQualification.driver_qualification_id == qualification_id)
        .with_for_update(key_share=True)
    ).scalar_one_or_none()
    if q is None:
        raise AppError("NOT_FOUND")
    driver = driver_in_scope(auth, q.driver_id)
    check_version(expected_version, q.row_version)
    if q.status != "VALID":
        raise AppError("STATE_TRANSITION_INVALID")
    q.status = body.status
    q.updated_by = auth.user_id
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="driver_qualification.revoke",
        entity_type="driver_qualification",
        entity_id=q.driver_qualification_id,
        site_id=driver.site_id,
        actor_user_id=auth.user_id,
        before={"status": "VALID"},
        after={"status": q.status},
        changed_fields=("status",),
    )
    out = _qualification_out(auth, q, driver.site_id)
    db.commit()
    return out


# --- Échéances ----------------------------------------------------------------------------------------


def expirations(auth: Authorized, within_days: int) -> list[ExpirationItem]:
    """US-1.20 : permis et habilitations EXPIRING ou EXPIRED dans la portée, triés par date."""
    db, now = auth.db, auth.clock.now()
    horizon = (now + timedelta(days=within_days + 1)).date()
    drivers_stmt = select(Driver)
    if not auth.scope.tenant_wide:
        drivers_stmt = drivers_stmt.where(Driver.site_id.in_(auth.scope.site_ids))
    drivers = {d.driver_id: d for d in db.execute(drivers_stmt).scalars()}
    if not drivers:
        return []
    zones: dict[uuid.UUID, Any] = {}
    items: list[ExpirationItem] = []

    def add(
        kind: str,
        item_id: uuid.UUID,
        driver_id: uuid.UUID,
        label: str,
        expires: Any,
        status: str,
        valid_from: Any,
    ) -> None:
        driver = drivers[driver_id]
        tz = zones.setdefault(driver.site_id, site_timezone(db, driver.site_id))
        validity = derive_validity(
            stored_status=status,
            valid_from=valid_from,
            valid_until=expires,
            now=now,
            tz=tz,
            warning_days=within_days,
        )
        if validity in ("EXPIRING", "EXPIRED"):
            items.append(
                ExpirationItem(
                    kind=kind,
                    item_id=item_id,
                    driver_id=driver_id,
                    employee_number=driver.employee_number,
                    driver_name=f"{driver.last_name} {driver.first_name}",
                    site_id=driver.site_id,
                    label=label,
                    expires_on=expires,
                    validity=validity,
                )
            )

    # Seule l'échéance la plus lointaine d'une même lignée compte : un permis renouvelé ou une
    # habilitation reconduite ne doit pas rester signalé « expiré » indéfiniment (QA1B-04).
    licenses = list(
        db.execute(
            select(DriverLicense).where(
                DriverLicense.driver_id.in_(list(drivers)), DriverLicense.status == "VALID"
            )
        ).scalars()
    )
    latest_license: dict[tuple[uuid.UUID, str], Any] = {}
    for lic in licenses:
        key = (lic.driver_id, lic.category_code)
        latest_license[key] = max(latest_license.get(key, lic.expiry_date), lic.expiry_date)
    for lic in licenses:
        if (
            lic.expiry_date <= horizon
            and lic.expiry_date == latest_license[(lic.driver_id, lic.category_code)]
        ):
            add(
                "LICENSE",
                lic.driver_license_id,
                lic.driver_id,
                f"Permis {lic.category_code}",
                lic.expiry_date,
                lic.status,
                lic.issue_date,
            )
    qualifications = list(
        db.execute(
            select(DriverQualification).where(
                DriverQualification.driver_id.in_(list(drivers)),
                DriverQualification.status == "VALID",
                DriverQualification.valid_to.is_not(None),
            )
        ).scalars()
    )
    latest_q: dict[tuple[Any, ...], Any] = {}
    for q in qualifications:
        if q.valid_to is None:  # exclu par la requête ; garde pour le typage
            continue
        key_q = (q.driver_id, q.qualification_type, q.vehicle_category_id, q.site_id)
        latest_q[key_q] = max(latest_q.get(key_q, q.valid_to), q.valid_to)
    for q in qualifications:
        key_q = (q.driver_id, q.qualification_type, q.vehicle_category_id, q.site_id)
        if q.valid_to is not None and q.valid_to <= horizon and q.valid_to == latest_q[key_q]:
            add(
                "QUALIFICATION",
                q.driver_qualification_id,
                q.driver_id,
                q.qualification_type,
                q.valid_to,
                q.status,
                q.valid_from,
            )
    return sorted(items, key=lambda i: (i.expires_on, i.driver_name, str(i.item_id)))
