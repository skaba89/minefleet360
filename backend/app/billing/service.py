"""Services du catalogue de plans SaaS (lot 1) et des abonnements (lot 2).

Règles clés (plans) :
- le code est immuable et unique (409 DUPLICATE_PLAN_CODE) ;
- RETIRED est un état terminal : plus aucune modification (422 PLAN_RETIRED) ;
- toute écriture est journalisée côté plateforme (tenant_id = PLATFORM_TENANT_ID).
Règles clés (abonnements) :
- un seul abonnement vivant par société (index unique partiel en base) ;
- écriture sous contexte RLS de la société cible, chaque transition audité.
L'application effective des quotas arrive avec le lot 2b ; ce lot livre le cycle de vie.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.billing.models import SaaSPlan, TenantSubscription
from app.billing.schemas import PlanCreate, PlanUpdate, SubscriptionCreate
from app.core.errors import AppError
from app.core.http import PageParams, check_version
from app.core.tenancy import PLATFORM_TENANT_ID, set_tenant_context
from app.organization.models import Tenant

PLAN_QUOTA_FIELDS = (
    "max_users",
    "max_sites",
    "max_vehicles",
    "max_gps_trackers",
    "document_retention_days",
)


def _snapshot(plan: SaaSPlan) -> dict[str, object]:
    return {
        "code": plan.code,
        "name": plan.name,
        "status": plan.status,
        **{field: getattr(plan, field) for field in PLAN_QUOTA_FIELDS},
    }


def create_plan(auth: Authorized, body: PlanCreate) -> SaaSPlan:
    db = auth.db
    duplicate = db.execute(
        select(func.count()).select_from(SaaSPlan).where(SaaSPlan.code == body.code)
    ).scalar_one()
    if duplicate:
        raise AppError("DUPLICATE_PLAN_CODE")
    plan = SaaSPlan(
        code=body.code,
        name=body.name,
        description=body.description,
        status=body.status,
        created_by=auth.user_id,
        updated_by=auth.user_id,
        **{field: getattr(body, field) for field in PLAN_QUOTA_FIELDS},
    )
    db.add(plan)
    db.flush()
    record(
        db,
        tenant_id=PLATFORM_TENANT_ID,
        action="billing.plan.create",
        entity_type="saas_plan",
        entity_id=plan.plan_id,
        actor_user_id=auth.user_id,
        after=_snapshot(plan),
    )
    db.commit()
    return plan


def list_plans(db: Session, page: PageParams) -> tuple[list[SaaSPlan], int]:
    total = db.execute(select(func.count()).select_from(SaaSPlan)).scalar_one()
    rows = db.execute(
        select(SaaSPlan).order_by(SaaSPlan.code, SaaSPlan.plan_id).offset(page.offset).limit(page.page_size)
    )
    return list(rows.scalars()), total


def get_plan(db: Session, plan_id: uuid.UUID) -> SaaSPlan:
    plan = db.get(SaaSPlan, plan_id)
    if plan is None:
        raise AppError("NOT_FOUND")
    return plan


def update_plan(auth: Authorized, plan_id: uuid.UUID, body: PlanUpdate, expected_version: int) -> SaaSPlan:
    db = auth.db
    plan = get_plan(db, plan_id)
    check_version(expected_version, plan.row_version)
    if plan.status == "RETIRED":
        raise AppError("PLAN_RETIRED")
    before = _snapshot(plan)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    clear_quotas = {
        field
        for field in PLAN_QUOTA_FIELDS
        if field in body.model_fields_set and getattr(body, field) is None
    }
    for field, value in changes.items():
        setattr(plan, field, value)
    for field in clear_quotas:  # explicite : quota remis à NULL = illimité
        setattr(plan, field, None)
    plan.updated_by = auth.user_id
    db.flush()
    after = _snapshot(plan)
    record(
        db,
        tenant_id=PLATFORM_TENANT_ID,
        action="billing.plan.update",
        entity_type="saas_plan",
        entity_id=plan.plan_id,
        actor_user_id=auth.user_id,
        before=before,
        after=after,
        changed_fields=[key for key in after if before[key] != after[key]],
    )
    db.commit()
    return plan


# --- Abonnements (lot 2) ------------------------------------------------------------------------------


def _live_subscription(db: Session, tenant_id: uuid.UUID) -> TenantSubscription | None:
    rows = db.execute(
        select(TenantSubscription)
        .where(TenantSubscription.tenant_id == tenant_id, TenantSubscription.status != "CANCELLED")
        .order_by(TenantSubscription.created_at.desc())
    )
    return rows.scalars().first()


def get_plan_for_platform(db: Session, plan_id: uuid.UUID) -> SaaSPlan:
    """Lit le plan hors contexte RLS (référentiel plateforme, table sans tenant_id)."""
    return get_plan(db, plan_id)


def create_subscription(
    auth: Authorized, tenant_id: uuid.UUID, body: SubscriptionCreate
) -> TenantSubscription:
    """Crée l'abonnement courant d'une société (TRIAL si trial_days, sinon ACTIVE).

    Un seul abonnement vivant par société : tout abonnement vivant existant est annulé
    (motif « remplacé ») avant création — l'historique est conservé. Le contexte RLS est
    basculé sur la société cible AVANT la lecture des abonnements existants (§6.2 point 4).
    """
    db, now = auth.db, auth.clock.now()
    target_tenant = db.get(Tenant, tenant_id)
    if target_tenant is None or target_tenant.kind != "CUSTOMER":
        raise AppError("NOT_FOUND")
    plan = get_plan(db, body.plan_id)
    if plan.status != "ACTIVE":
        raise AppError("PLAN_NOT_ACTIVE")
    # Contexte RLS : lecture et écriture dans la société cible — chaque écriture est auditée.
    set_tenant_context(db, tenant_id)
    previous = _live_subscription(db, tenant_id)
    if previous is not None:
        previous_status = previous.status
        previous.status = "CANCELLED"
        previous.cancelled_at = now
        previous.updated_by = auth.user_id
        record(
            db,
            tenant_id=tenant_id,
            action="billing.subscription.cancel",
            entity_type="tenant_subscription",
            entity_id=previous.subscription_id,
            actor_user_id=auth.user_id,
            reason="Remplacé par un nouvel abonnement",
            before={"status": previous_status},
            after={"status": "CANCELLED"},
            changed_fields=["status", "cancelled_at"],
        )
    status = "TRIAL" if body.trial_days is not None else "ACTIVE"
    subscription = TenantSubscription(
        tenant_id=tenant_id,
        plan_id=plan.plan_id,
        status=status,
        trial_ends_at=(now + timedelta(days=body.trial_days)) if body.trial_days is not None else None,
        period_ends_at=body.period_ends_at,
        notes=body.notes,
        created_by=auth.user_id,
        updated_by=auth.user_id,
    )
    db.add(subscription)
    db.flush()
    record(
        db,
        tenant_id=tenant_id,
        action="billing.subscription.create",
        entity_type="tenant_subscription",
        entity_id=subscription.subscription_id,
        actor_user_id=auth.user_id,
        after={
            "plan_code": plan.code,
            "status": status,
            "trial_ends_at": subscription.trial_ends_at.isoformat() if subscription.trial_ends_at else None,
        },
    )
    db.commit()
    return subscription


def _get_subscription_in_tenant(
    db: Session, tenant_id: uuid.UUID, subscription_id: uuid.UUID
) -> TenantSubscription:
    """Lit un abonnement APRÈS bascule du contexte RLS sur la société cible.

    L'appartenance de l'abonnement au tenant du chemin est vérifiée par la RLS elle-même :
    un identifiant d'une autre société est indiscernable d'un identifiant inexistant (404).
    """
    subscription = db.execute(
        select(TenantSubscription).where(
            TenantSubscription.subscription_id == subscription_id,
            TenantSubscription.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if subscription is None:
        raise AppError("NOT_FOUND")
    return subscription


def list_subscriptions(
    db: Session, tenant_id: uuid.UUID, page: PageParams, status_filter: str | None
) -> tuple[list[TenantSubscription], int]:
    set_tenant_context(db, tenant_id)
    base = select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
    if status_filter:
        base = base.where(TenantSubscription.status == status_filter)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        base.order_by(TenantSubscription.created_at.desc(), TenantSubscription.subscription_id)
        .offset(page.offset)
        .limit(page.page_size)
    )
    return list(rows.scalars()), total


def change_subscription_status(
    auth: Authorized,
    tenant_id: uuid.UUID,
    subscription_id: uuid.UUID,
    expected_version: int,
    target: str,
    reason: str | None,
) -> TenantSubscription:
    """Transitions : TRIAL/ACTIVE → SUSPENDED (motif), SUSPENDED → ACTIVE, vivant → CANCELLED."""
    db, now = auth.db, auth.clock.now()
    set_tenant_context(db, tenant_id)
    subscription = _get_subscription_in_tenant(db, tenant_id, subscription_id)
    check_version(expected_version, subscription.row_version)
    allowed = {
        ("TRIAL", "ACTIVE"),
        ("TRIAL", "SUSPENDED"),
        ("ACTIVE", "SUSPENDED"),
        ("SUSPENDED", "ACTIVE"),
        ("TRIAL", "CANCELLED"),
        ("ACTIVE", "CANCELLED"),
        ("SUSPENDED", "CANCELLED"),
    }
    if (subscription.status, target) not in allowed:
        raise AppError("STATE_TRANSITION_INVALID")
    before = {"status": subscription.status}
    subscription.status = target
    if target == "SUSPENDED":
        subscription.suspended_at = now
        subscription.suspension_reason = reason
    else:
        subscription.suspended_at = None
        subscription.suspension_reason = None
        if target == "CANCELLED":
            subscription.cancelled_at = now
    subscription.updated_by = auth.user_id
    db.flush()
    record(
        db,
        tenant_id=tenant_id,
        action=f"billing.subscription.{target.lower()}",
        entity_type="tenant_subscription",
        entity_id=subscription.subscription_id,
        actor_user_id=auth.user_id,
        reason=reason,
        before=before,
        after={"status": target},
        changed_fields=["status"],
    )
    db.commit()
    return subscription


def renew_subscription(
    auth: Authorized,
    tenant_id: uuid.UUID,
    subscription_id: uuid.UUID,
    expected_version: int,
    period_ends_at: datetime,
) -> TenantSubscription:
    """Prolonge (ou fixe) la période courante d'un abonnement vivant — renouvellement manuel."""
    db = auth.db
    set_tenant_context(db, tenant_id)
    subscription = _get_subscription_in_tenant(db, tenant_id, subscription_id)
    check_version(expected_version, subscription.row_version)
    if subscription.status == "CANCELLED":
        raise AppError("STATE_TRANSITION_INVALID")
    subscription.period_ends_at = period_ends_at
    subscription.updated_by = auth.user_id
    db.flush()
    record(
        db,
        tenant_id=subscription.tenant_id,
        action="billing.subscription.renew",
        entity_type="tenant_subscription",
        entity_id=subscription.subscription_id,
        actor_user_id=auth.user_id,
        after={"period_ends_at": period_ends_at.isoformat()},
        changed_fields=["period_ends_at"],
    )
    db.commit()
    return subscription


def read_own_subscription(db: Session, tenant_id: uuid.UUID) -> TenantSubscription:
    """Abonnement courant de la société appelante (404 neutre si aucun — pas d'énumération)."""
    subscription = _live_subscription(db, tenant_id)
    if subscription is None:
        raise AppError("NOT_FOUND")
    return subscription
