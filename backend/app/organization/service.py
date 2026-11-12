"""Services organisation : provisioning et suspension de tenant (plateforme), tenant courant, sites,
vue support consolidée, parcours d'onboarding et export de réversibilité (lot 4 commercialisation)."""

import logging
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.billing.models import BillingInvoice, SaaSPlan, TenantSubscription
from app.billing.quotas import ensure_quota
from app.billing.schemas import PlanSummary
from app.core.config import Settings, get_settings
from app.core.email import EmailMessage
from app.core.errors import AppError
from app.core.http import PageParams, check_version
from app.core.logging import security_logger
from app.core.tenancy import PLATFORM_TENANT_ID, set_tenant_context
from app.fleet.contracts import seed_tenant_catalog
from app.fleet.contracts import site_blockers as fleet_site_blockers
from app.fleet.models import Vehicle
from app.identity.contracts import create_invited_user, invitation_message, revoke_sessions
from app.identity.models import UserAccount, UserRoleAssignment
from app.organization.models import Site, Tenant
from app.organization.schemas import (
    OnboardingChecklistOut,
    OnboardingStepOut,
    OverviewInvoice,
    OverviewUsage,
    OverviewUsers,
    SiteCreate,
    SiteUpdate,
    TenantCreate,
    TenantOverviewOut,
    TenantSubscriptionOut,
    TenantSummary,
    TenantUpdate,
)
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
    """Lot 2b : refus (422 QUOTA_EXCEEDED) si la borne `max_sites` de la formule vivante est atteinte."""
    ensure_quota(auth, "max_sites")
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


# --- Lot 4 commercialisation : support plateforme, onboarding, réversibilité ---------------------------

SUPPORT_USAGE_LABELS: dict[str, str] = {
    "max_users": "Utilisateurs",
    "max_sites": "Sites",
    "max_vehicles": "Véhicules",
    "max_gps_trackers": "Traceurs GPS",
}

EXPORT_FORMAT_VERSION = 1


def _live_subscription(db: Session, tenant_id: uuid.UUID) -> TenantSubscription | None:
    return (
        db.execute(
            select(TenantSubscription)
            .where(TenantSubscription.tenant_id == tenant_id)
            .order_by(TenantSubscription.created_at.desc(), TenantSubscription.subscription_id)
        )
        .scalars()
        .first()
    )


def tenant_overview(auth: Authorized, tenant_id: uuid.UUID) -> TenantOverviewOut:
    """Vue consolidée d'exploitation d'un compte client (outillage support, calculée à la lecture).

    Regroupe : société, abonnement courant (statut effectif, plan et quotas), usage réel vs
    limites, comptes utilisateurs et factures récentes. Aucune persistance, aucun audit
    (lecture d'exploitation). Le contexte RLS du tenant cible est posé le temps de la lecture.
    """
    from app.billing.quotas import usage_counts
    from app.billing.service import effective_status

    db = auth.db
    tenant = get_customer_tenant(db, tenant_id)
    set_tenant_context(db, tenant_id)
    subscription_out: TenantSubscriptionOut | None = None
    usage_limit_by_field: dict[str, int | None] = {field: None for field in SUPPORT_USAGE_LABELS}
    subscription = _live_subscription(db, tenant_id)
    if subscription is not None:
        plan = db.get(SaaSPlan, subscription.plan_id)
        if plan is not None:
            usage_limit_by_field = {field: getattr(plan, field) for field in SUPPORT_USAGE_LABELS}
        subscription_out = TenantSubscriptionOut(
            subscription_id=subscription.subscription_id,
            status=subscription.status,
            effective_status=effective_status(subscription, auth.clock.now()),
            trial_ends_at=subscription.trial_ends_at,
            period_ends_at=subscription.period_ends_at,
            plan=PlanSummary.model_validate(plan, from_attributes=True),
        )
    usage = usage_counts(db, tenant_id)
    users_active = db.execute(
        select(func.count())
        .select_from(UserAccount)
        .where(
            UserAccount.tenant_id == tenant_id,
            UserAccount.status == "ACTIVE",
            UserAccount.anonymized_at.is_(None),
        )
    ).scalar_one()
    users_invited = db.execute(
        select(func.count())
        .select_from(UserAccount)
        .where(
            UserAccount.tenant_id == tenant_id,
            UserAccount.status == "INVITED",
            UserAccount.anonymized_at.is_(None),
        )
    ).scalar_one()
    users_disabled = db.execute(
        select(func.count())
        .select_from(UserAccount)
        .where(UserAccount.tenant_id == tenant_id, UserAccount.status == "DISABLED")
    ).scalar_one()
    invoices = (
        db.execute(
            select(BillingInvoice)
            .where(BillingInvoice.tenant_id == tenant_id)
            .order_by(BillingInvoice.created_at.desc(), BillingInvoice.invoice_id)
            .limit(5)
        )
        .scalars()
        .all()
    )
    return TenantOverviewOut(
        tenant=TenantSummary.model_validate(tenant, from_attributes=True),
        subscription=subscription_out,
        usage=[
            OverviewUsage(field=field, label=label, usage=usage[field], limit=usage_limit_by_field[field])
            for field, label in SUPPORT_USAGE_LABELS.items()
        ],
        users=OverviewUsers(active=users_active, invited=users_invited, disabled=users_disabled),
        invoices=[
            OverviewInvoice(
                invoice_id=invoice.invoice_id,
                number=invoice.number,
                status=invoice.status,
                total_gnf=invoice.total_gnf,
                created_at=invoice.created_at,
            )
            for invoice in invoices
        ],
    )


def onboarding_checklist(auth: Authorized) -> OnboardingChecklistOut:
    """Parcours de démarrage de la société : étapes calculées depuis l'état réel, aucune persistance.

    Chaque étape compare un compteur réel (usage, abonnement vivant) à un objectif minimal ;
    la progression ne se « valide » jamais manuellement — c'est le comportement constaté qui
    fait avancer la checklist (aucun état à maintenir en base).
    """
    from app.billing.quotas import usage_counts

    db = auth.db
    usage = usage_counts(db, auth.tenant_id)
    subscription_alive = (
        db.execute(
            select(func.count())
            .select_from(TenantSubscription)
            .where(
                TenantSubscription.tenant_id == auth.tenant_id,
                TenantSubscription.status.in_(("TRIAL", "ACTIVE", "SUSPENDED")),
            )
        ).scalar_one()
        > 0
    )
    definitions: tuple[tuple[str, str, str, int, int], ...] = (
        (
            "subscription",
            "Essai ou abonnement actif",
            "La plateforme active un essai ou un abonnement pour votre société.",
            1,
            1 if subscription_alive else 0,
        ),
        (
            "users",
            "Votre équipe est invitée",
            "Au moins deux utilisateurs actifs (l'administrateur et un collègue).",
            2,
            usage["max_users"],
        ),
        (
            "sites",
            "Vos sites sont créés",
            "Créez au moins un site (mine, carrière, dépôt…).",
            1,
            usage["max_sites"],
        ),
        (
            "vehicles",
            "Votre flotte est enregistrée",
            "Enregistrez au moins un véhicule actif.",
            1,
            usage["max_vehicles"],
        ),
        (
            "gps_trackers",
            "Vos véhicules sont équipés",
            "Liez au moins un traceur GPS à un véhicule pour le suivi temps réel.",
            1,
            usage["max_gps_trackers"],
        ),
    )
    steps = [
        OnboardingStepOut(key=key, label=label, hint=hint, target=target, count=count, done=count >= target)
        for key, label, hint, target, count in definitions
    ]
    done = sum(1 for step in steps if step.done)
    total = len(steps)
    return OnboardingChecklistOut(
        steps=steps,
        done_count=done,
        total=total,
        progress_percent=round(done / total * 100),
    )


def export_tenant_data(auth: Authorized) -> dict[str, Any]:
    """Réversibilité (lot 4) : export JSON des données de la société, journalisé, sans aucun secret.

    Ne contient jamais d'attribut d'authentification (hachage de mot de passe, secrets MFA,
    antenne de sessions) ni de métadonnées d'exploitation plateforme. Les comptes anonymisés
    sont exclus (seul leur témoignage de suppression resterait pertinent, pas leur donnée).
    """
    from app.billing.models import BillingInvoiceLine

    db = auth.db
    tenant = db.get(Tenant, auth.tenant_id)
    if tenant is None:
        raise AppError("NOT_FOUND")
    sites = (
        db.execute(select(Site).where(Site.tenant_id == auth.tenant_id).order_by(Site.code)).scalars().all()
    )
    users = (
        db.execute(
            select(UserAccount)
            .where(UserAccount.tenant_id == auth.tenant_id, UserAccount.anonymized_at.is_(None))
            .order_by(UserAccount.email)
        )
        .scalars()
        .all()
    )
    role_assignments = (
        db.execute(
            select(UserRoleAssignment)
            .where(
                UserRoleAssignment.tenant_id == auth.tenant_id,
                UserRoleAssignment.revoked_at.is_(None),
            )
            .order_by(UserRoleAssignment.user_account_id, UserRoleAssignment.role_code)
        )
        .scalars()
        .all()
    )
    roles_by_user: dict[uuid.UUID, list[str]] = {}
    for assignment in role_assignments:
        roles_by_user.setdefault(assignment.user_account_id, []).append(assignment.role_code)
    vehicles = (
        db.execute(select(Vehicle).where(Vehicle.tenant_id == auth.tenant_id).order_by(Vehicle.fleet_number))
        .scalars()
        .all()
    )
    subscriptions = (
        db.execute(
            select(TenantSubscription)
            .where(TenantSubscription.tenant_id == auth.tenant_id)
            .order_by(TenantSubscription.created_at, TenantSubscription.subscription_id)
        )
        .scalars()
        .all()
    )
    invoices = (
        db.execute(
            select(BillingInvoice)
            .where(BillingInvoice.tenant_id == auth.tenant_id)
            .order_by(BillingInvoice.created_at, BillingInvoice.invoice_id)
        )
        .scalars()
        .all()
    )
    lines_by_invoice: dict[uuid.UUID, list[BillingInvoiceLine]] = {}
    if invoices:
        invoice_ids = [invoice.invoice_id for invoice in invoices]
        lines = (
            db.execute(
                select(BillingInvoiceLine)
                .where(BillingInvoiceLine.invoice_id.in_(invoice_ids))
                .order_by(BillingInvoiceLine.invoice_id, BillingInvoiceLine.line_number)
            )
            .scalars()
            .all()
        )
        for line in lines:
            lines_by_invoice.setdefault(line.invoice_id, []).append(line)

    record(
        db,
        tenant_id=auth.tenant_id,
        action="tenant.export",
        entity_type="tenant",
        entity_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        after={
            "sites": len(sites),
            "users": len(users),
            "vehicles": len(vehicles),
            "subscriptions": len(subscriptions),
            "invoices": len(invoices),
        },
    )
    return {
        "format_version": EXPORT_FORMAT_VERSION,
        "exported_at": auth.clock.now().isoformat(),
        "tenant": {
            "code": tenant.code,
            "legal_name": tenant.legal_name,
            "display_name": tenant.display_name,
            "status": tenant.status,
            "default_timezone": tenant.default_timezone,
            "default_locale": tenant.default_locale,
            "currency_code": tenant.currency_code,
            "country_code": tenant.country_code,
            "created_at": tenant.created_at,
        },
        "sites": [
            {
                "site_id": str(site.site_id),
                "code": site.code,
                "name": site.name,
                "site_type": site.site_type,
                "timezone": site.timezone,
                "status": site.status,
                "created_at": site.created_at,
            }
            for site in sites
        ],
        "users": [
            {
                "user_account_id": str(user.user_account_id),
                "email": user.email,
                "display_name": user.display_name,
                "status": user.status,
                "roles": roles_by_user.get(user.user_account_id, []),
                "created_at": user.created_at,
            }
            for user in users
        ],
        "vehicles": [
            {
                "vehicle_id": str(vehicle.vehicle_id),
                "site_id": str(vehicle.site_id),
                "fleet_number": vehicle.fleet_number,
                "registration_number": vehicle.registration_number,
                "make": vehicle.make,
                "model": vehicle.model,
                "model_year": vehicle.model_year,
                "fuel_type": vehicle.fuel_type,
                "status": vehicle.status,
                "created_at": vehicle.created_at,
            }
            for vehicle in vehicles
        ],
        "subscriptions": [
            {
                "subscription_id": str(subscription.subscription_id),
                "plan_id": str(subscription.plan_id),
                "status": subscription.status,
                "trial_ends_at": subscription.trial_ends_at,
                "period_ends_at": subscription.period_ends_at,
                "created_at": subscription.created_at,
            }
            for subscription in subscriptions
        ],
        "invoices": [
            {
                "invoice_id": str(invoice.invoice_id),
                "number": invoice.number,
                "status": invoice.status,
                "currency": invoice.currency,
                "tax_rate_bp": invoice.tax_rate_bp,
                "subtotal_gnf": invoice.subtotal_gnf,
                "tax_gnf": invoice.tax_gnf,
                "total_gnf": invoice.total_gnf,
                "created_at": invoice.created_at,
                "lines": [
                    {
                        "description": line.description,
                        "quantity": line.quantity,
                        "unit_price_gnf": line.unit_price_gnf,
                        "amount_gnf": line.amount_gnf,
                    }
                    for line in lines_by_invoice.get(invoice.invoice_id, [])
                ],
            }
            for invoice in invoices
        ],
    }
