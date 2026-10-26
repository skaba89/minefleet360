"""Services organisation : provisioning et suspension de tenant (plateforme), tenant courant, sites."""

import logging
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.config import Settings, get_settings
from app.core.email import EmailMessage
from app.core.errors import AppError
from app.core.http import PageParams, check_version
from app.core.logging import security_logger
from app.core.tenancy import PLATFORM_TENANT_ID, set_tenant_context
from app.fleet.contracts import seed_tenant_catalog
from app.fleet.contracts import site_blockers as fleet_site_blockers
from app.identity.contracts import create_invited_user, invitation_message, revoke_sessions
from app.organization.models import Site, Tenant
from app.organization.schemas import SiteCreate, SiteUpdate, TenantCreate, TenantUpdate
from app.workforce.contracts import site_blockers as workforce_site_blockers

logger = logging.getLogger("minefleet.organization")


def _snapshot(obj: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {name: getattr(obj, name) for name in fields}


# --- Plateforme --------------------------------------------------------------------------------------


def create_tenant(auth: Authorized, body: TenantCreate, settings: Settings) -> tuple[Tenant, EmailMessage]:
    """US-1.01 : tenant + premier TENANT_ADMIN invité, dans UNE transaction, audité des deux côtés.

    Les catégories de véhicule (et permis requis) sont copiées du catalogue de référence (D-18).
    """
    if body.code in settings.reserved_tenant_codes:
        raise AppError("TENANT_CODE_RESERVED")
    db, now = auth.db, auth.clock.now()
    tenant = Tenant(
        code=body.code,
        kind="CUSTOMER",
        legal_name=body.legal_name,
        display_name=body.display_name,
        default_timezone=body.default_timezone,
        created_by=auth.user_id,
        updated_by=auth.user_id,
    )
    db.add(tenant)
    db.flush()
    record(
        db,
        tenant_id=PLATFORM_TENANT_ID,
        action="tenant.create",
        entity_type="tenant",
        entity_id=tenant.tenant_id,
        actor_user_id=auth.user_id,
        after={"code": tenant.code, "display_name": tenant.display_name},
    )
    # Changement de contexte unique et audité (MODELE_PHYSIQUE §6.2 point 4).
    set_tenant_context(db, tenant.tenant_id)
    categories = seed_tenant_catalog(db, tenant.tenant_id)
    admin, _, token = create_invited_user(
        db,
        tenant_id=tenant.tenant_id,
        tenant_kind="CUSTOMER",
        email=str(body.admin_email),
        display_name=body.admin_display_name,
        phone=None,
        role_code="TENANT_ADMIN",
        scope_type="TENANT",
        site_id=None,
        granted_by=auth.user_id,
        now=now,
        settings=settings,
    )
    record(
        db,
        tenant_id=tenant.tenant_id,
        action="tenant.provision",
        entity_type="tenant",
        entity_id=tenant.tenant_id,
        actor_user_id=auth.user_id,
        after={
            "code": tenant.code,
            "first_admin_user_id": admin.user_account_id,
            "vehicle_categories_copied": categories,
            "criticality": "HIGH",
        },
    )
    db.commit()
    return tenant, invitation_message(str(body.admin_email), token, tenant.code, settings)


def list_tenants(db: Session, page: PageParams) -> tuple[list[Tenant], int]:
    base = select(Tenant).where(Tenant.kind == "CUSTOMER")
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(base.order_by(Tenant.code, Tenant.tenant_id).offset(page.offset).limit(page.page_size))
    return list(rows.scalars()), total


def get_customer_tenant(db: Session, tenant_id: uuid.UUID) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None or tenant.kind != "CUSTOMER":
        raise AppError("NOT_FOUND")
    return tenant


def change_tenant_status(
    auth: Authorized, tenant_id: uuid.UUID, expected_version: int, target: str, reason: str
) -> Tenant:
    """US-1.02 : suspension (révocation de toutes les sessions) ou réactivation, auditées."""
    db, now = auth.db, auth.clock.now()
    if tenant_id == PLATFORM_TENANT_ID:
        raise AppError("VALIDATION_ERROR", details=[{"field": "tenant_id", "type": "platform_tenant"}])
    tenant = db.execute(
        select(Tenant)
        .where(Tenant.tenant_id == tenant_id, Tenant.kind == "CUSTOMER")
        .with_for_update(key_share=True)
    ).scalar_one_or_none()
    if tenant is None:
        raise AppError("NOT_FOUND")
    check_version(expected_version, tenant.row_version)
    source = "ACTIVE" if target == "SUSPENDED" else "SUSPENDED"
    if tenant.status != source:
        raise AppError("STATE_TRANSITION_INVALID")
    tenant.status = target
    tenant.updated_by = auth.user_id
    db.flush()
    action = "tenant.suspend" if target == "SUSPENDED" else "tenant.reactivate"
    record(
        db,
        tenant_id=PLATFORM_TENANT_ID,
        action=action,
        entity_type="tenant",
        entity_id=tenant.tenant_id,
        actor_user_id=auth.user_id,
        reason=reason,
        before={"status": source},
        after={"status": target},
    )
    set_tenant_context(db, tenant.tenant_id)
    revoked = revoke_sessions(db, now=now, reason="TENANT_SUSPENDED") if target == "SUSPENDED" else 0
    record(
        db,
        tenant_id=tenant.tenant_id,
        action=action,
        entity_type="tenant",
        entity_id=tenant.tenant_id,
        actor_user_id=auth.user_id,
        reason=reason,
        before={"status": source},
        after={"status": target, "sessions_revoked": revoked},
    )
    db.commit()
    return tenant


# --- Tenant courant -----------------------------------------------------------------------------------


def get_own_tenant(auth: Authorized) -> Tenant:
    tenant = auth.db.get(Tenant, auth.tenant_id)
    if tenant is None:  # impossible sous RLS avec une session valide
        raise AppError("NOT_FOUND")
    return tenant


def update_own_tenant(auth: Authorized, body: TenantUpdate, expected_version: int) -> Tenant:
    db = auth.db
    tenant = db.execute(
        select(Tenant).where(Tenant.tenant_id == auth.tenant_id).with_for_update(key_share=True)
    ).scalar_one()
    check_version(expected_version, tenant.row_version)
    fields = tuple(name for name in body.model_fields_set if getattr(body, name) is not None)
    before = _snapshot(tenant, fields)
    for name in fields:
        setattr(tenant, name, getattr(body, name))
    tenant.updated_by = auth.user_id
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="tenant.update",
        entity_type="tenant",
        entity_id=tenant.tenant_id,
        actor_user_id=auth.user_id,
        before=before,
        after=_snapshot(tenant, fields),
        changed_fields=fields,
    )
    db.commit()
    return tenant


# --- Sites --------------------------------------------------------------------------------------------

_SITE_FIELDS = ("code", "name", "site_type", "timezone", "status")


def _site_in_scope(auth: Authorized, site_id: uuid.UUID, *, for_update: bool = False) -> Site:
    """404 identique pour : inexistant, autre tenant (invisible sous RLS), hors portée de site."""
    stmt = select(Site).where(Site.site_id == site_id)
    if for_update:
        stmt = stmt.with_for_update(key_share=True)
    site = auth.db.execute(stmt).scalar_one_or_none()
    if site is None or not auth.scope.covers_site(site.site_id):
        security_logger.info(
            "item_not_found",
            extra={"entity_type": "site", "entity_id": str(site_id), "tenant_id": str(auth.tenant_id)},
        )
        raise AppError("NOT_FOUND")
    return site


def list_sites(auth: Authorized, page: PageParams, status: str | None) -> tuple[list[Site], int]:
    stmt = select(Site)
    if not auth.scope.tenant_wide:
        stmt = stmt.where(Site.site_id.in_(auth.scope.site_ids))
    if status is not None:
        stmt = stmt.where(Site.status == status)
    total = auth.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = auth.db.execute(stmt.order_by(Site.code, Site.site_id).offset(page.offset).limit(page.page_size))
    return list(rows.scalars()), total


def get_site(auth: Authorized, site_id: uuid.UUID) -> Site:
    return _site_in_scope(auth, site_id)


def create_site(auth: Authorized, body: SiteCreate) -> Site:
    db = auth.db
    site = Site(
        tenant_id=auth.tenant_id,
        code=body.code,
        name=body.name,
        site_type=body.site_type,
        timezone=body.timezone,
        created_by=auth.user_id,
        updated_by=auth.user_id,
    )
    db.add(site)
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="site.create",
        entity_type="site",
        entity_id=site.site_id,
        site_id=site.site_id,
        actor_user_id=auth.user_id,
        after=_snapshot(site, _SITE_FIELDS),
    )
    db.commit()
    return site


def update_site(auth: Authorized, site_id: uuid.UUID, body: SiteUpdate, expected_version: int) -> Site:
    db = auth.db
    site = _site_in_scope(auth, site_id, for_update=True)
    check_version(expected_version, site.row_version)
    fields = tuple(
        name for name in body.model_fields_set if name != "timezone" and getattr(body, name) is not None
    )
    if "timezone" in body.model_fields_set:
        fields = (*fields, "timezone")  # null explicite = revenir au fuseau du tenant
    before = _snapshot(site, fields)
    for name in fields:
        setattr(site, name, getattr(body, name))
    site.updated_by = auth.user_id
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="site.update",
        entity_type="site",
        entity_id=site.site_id,
        site_id=site.site_id,
        actor_user_id=auth.user_id,
        before=before,
        after=_snapshot(site, fields),
        changed_fields=fields,
    )
    db.commit()
    return site


def _site_blockers(db: Session, site_id: uuid.UUID) -> tuple[int, list[dict[str, str]]]:
    """Contrats publics uniquement; total exact et liste bornée sans identité personnelle."""
    limit = get_settings().blocking_list_max
    fleet_total, fleet_items = fleet_site_blockers(db, site_id, limit)
    driver_total, driver_items = workforce_site_blockers(db, site_id, max(0, limit - len(fleet_items)))
    return fleet_total + driver_total, fleet_items + driver_items


def change_site_status(auth: Authorized, site_id: uuid.UUID, expected_version: int, target: str) -> Site:
    db = auth.db
    site = _site_in_scope(auth, site_id, for_update=True)
    check_version(expected_version, site.row_version)
    source = "ACTIVE" if target == "INACTIVE" else "INACTIVE"
    if site.status != source:
        raise AppError("STATE_TRANSITION_INVALID")
    if target == "INACTIVE":
        total, blockers = _site_blockers(db, site.site_id)
        if total:
            raise AppError(
                "SITE_HAS_ACTIVE_RESOURCES",
                details={"total": total, "items": blockers},
            )
    site.status = target
    site.updated_by = auth.user_id
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="site.deactivate" if target == "INACTIVE" else "site.reactivate",
        entity_type="site",
        entity_id=site.site_id,
        site_id=site.site_id,
        actor_user_id=auth.user_id,
        before={"status": source},
        after={"status": target},
        changed_fields=("status",),
    )
    db.commit()
    return site
