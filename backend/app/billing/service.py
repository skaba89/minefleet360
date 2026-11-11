"""Services du catalogue de plans SaaS (lot 1), abonnements (lot 2) et facturation (lot 3).

Règles clés (plans) :
- le code est immuable et unique (409 DUPLICATE_PLAN_CODE) ;
- RETIRED est un état terminal : plus aucune modification (422 PLAN_RETIRED) ;
- toute écriture est journalisée côté plateforme (tenant_id = PLATFORM_TENANT_ID).
Règles clés (abonnements) :
- un seul abonnement vivant par société (index unique partiel en base) ;
- écriture sous contexte RLS de la société cible, chaque transition audité.
- l'expiration d'un essai daté est un statut EFFECTIF calculé à la lecture (EXPIRED) : aucun
  scheduler n'altère le statut stocké (décision lot 3, voir LIVRAISON_SAAS_FACTURATION.md).
Règles clés (facturation) :
- document interne de traçabilité : DRAFT → ISSUED → VOIDED (terminal), aucun encaissement ;
- numérotation plateforme atomique par année (MF-<année>-<numéro>) ;
- montants GNF figés à la création, lignes immuables, taxe en points de base.
L'application effective des quotas au provisionnement reste au lot 2b.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.billing.models import (
    BillingInvoice,
    BillingInvoiceLine,
    SaaSPlan,
    TenantSubscription,
)
from app.billing.schemas import (
    InvoiceCreate,
    InvoiceLineIn,
    PlanCreate,
    PlanUpdate,
    SubscriptionCreate,
)
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
PLAN_PRICING_FIELDS = ("price_monthly_gnf", "billing_period")


def _snapshot(plan: SaaSPlan) -> dict[str, object]:
    return {
        "code": plan.code,
        "name": plan.name,
        "status": plan.status,
        **{field: getattr(plan, field) for field in PLAN_QUOTA_FIELDS},
        **{field: getattr(plan, field) for field in PLAN_PRICING_FIELDS},
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
        **{field: getattr(body, field) for field in PLAN_PRICING_FIELDS},
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
    clear_pricing = {
        field
        for field in PLAN_PRICING_FIELDS
        if field in body.model_fields_set and getattr(body, field) is None
    }
    for field, value in changes.items():
        setattr(plan, field, value)
    for field in clear_quotas | clear_pricing:  # explicite : remis à NULL (illimité / non tarifé)
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
    # NOTE (lot 3) : un essai EXPIRED (statut effectif) reste transitionnable : le statut stocké TRIAL.
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


# --- Statut effectif de l'abonnement (lot 3) ----------------------------------------------------------


def effective_status(subscription: TenantSubscription, now: datetime) -> str:
    """Statut calculé à la lecture : un essai daté échue s'affiche EXPIRED sans écrire en base.

    Le statut stocké reste TRIAL (aucun scheduler, aucune écriture implicite) : la plateforme
    décide de la transition (activation, suspension, annulation). CANCELLED reste terminal.
    """
    if (
        subscription.status == "TRIAL"
        and subscription.trial_ends_at is not None
        and subscription.trial_ends_at < now
    ):
        return "EXPIRED"
    return subscription.status


# --- Facturation (lot 3) ------------------------------------------------------------------------------


def _next_invoice_number(db: Session, year: int) -> str:
    """Numéro lisible MF-<année>-<numéro> : incrémentation atomique en base (upsert + RETURNING)."""
    number = db.execute(
        text(
            "INSERT INTO billing_invoice_sequence (year, last_number) VALUES (:year, 1)"
            " ON CONFLICT (year) DO UPDATE SET last_number = billing_invoice_sequence.last_number + 1"
            " RETURNING last_number"
        ),
        {"year": year},
    ).scalar_one()
    return f"MF-{year}-{number:05d}"


def _invoice_amounts(lines: list[InvoiceLineIn], tax_rate_bp: int) -> tuple[int, int, int]:
    subtotal = sum(line.quantity * line.unit_price_gnf for line in lines)
    # GNF : pas de subdivision ; arrondi à l'unité la plus proche (taxe en points de base).
    tax = (subtotal * tax_rate_bp + 5_000) // 10_000
    return subtotal, tax, subtotal + tax


def _get_invoice_in_tenant(db: Session, tenant_id: uuid.UUID, invoice_id: uuid.UUID) -> BillingInvoice:
    """Lit une facture APRÈS bascule du contexte RLS (404 identique pour cross-tenant et inconnu)."""
    invoice = db.execute(
        select(BillingInvoice).where(
            BillingInvoice.invoice_id == invoice_id, BillingInvoice.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    if invoice is None:
        raise AppError("NOT_FOUND")
    return invoice


def create_invoice(auth: Authorized, tenant_id: uuid.UUID, body: InvoiceCreate) -> BillingInvoice:
    """Crée une facture DRAFT (lignes fournies ou préremplies depuis le tarif du plan)."""
    db, now = auth.db, auth.clock.now()
    target_tenant = db.get(Tenant, tenant_id)
    if target_tenant is None or target_tenant.kind != "CUSTOMER":
        raise AppError("NOT_FOUND")
    lines = list(body.lines)
    if body.subscription_id is not None:
        set_tenant_context(db, tenant_id)
        subscription = _get_subscription_in_tenant(db, tenant_id, body.subscription_id)
        if subscription.status == "CANCELLED":
            raise AppError("SUBSCRIPTION_CANCELLED")
        plan = get_plan(db, subscription.plan_id)
        if not lines:
            if plan.price_monthly_gnf is None:
                raise AppError("PLAN_NOT_PRICED")
            lines = [
                InvoiceLineIn(
                    description=f"Abonnement MineFleet 360 — plan {plan.name} ({plan.code})",
                    quantity=1,
                    unit_price_gnf=plan.price_monthly_gnf,
                )
            ]
    if not lines:
        raise AppError("INVOICE_LINES_REQUIRED")
    set_tenant_context(db, tenant_id)
    subtotal, tax, total = _invoice_amounts(lines, body.tax_rate_bp)
    invoice = BillingInvoice(
        tenant_id=tenant_id,
        subscription_id=body.subscription_id,
        number=_next_invoice_number(db, now.year),
        status="DRAFT",
        tax_rate_bp=body.tax_rate_bp,
        period_start=body.period_start,
        period_end=body.period_end,
        notes=body.notes,
        created_by=auth.user_id,
        updated_by=auth.user_id,
        subtotal_gnf=subtotal,
        tax_gnf=tax,
        total_gnf=total,
    )
    db.add(invoice)
    db.flush()
    db.add_all(
        BillingInvoiceLine(
            invoice_id=invoice.invoice_id,
            tenant_id=tenant_id,
            line_number=position,
            description=line.description,
            quantity=line.quantity,
            unit_price_gnf=line.unit_price_gnf,
            amount_gnf=line.quantity * line.unit_price_gnf,
            created_by=auth.user_id,
        )
        for position, line in enumerate(lines, start=1)
    )
    db.flush()
    record(
        db,
        tenant_id=tenant_id,
        action="billing.invoice.create",
        entity_type="billing_invoice",
        entity_id=invoice.invoice_id,
        actor_user_id=auth.user_id,
        after={"number": invoice.number, "total_gnf": invoice.total_gnf, "status": "DRAFT"},
    )
    db.commit()
    return invoice


def list_invoices(
    db: Session, tenant_id: uuid.UUID, page: PageParams, status_filter: str | None
) -> tuple[list[BillingInvoice], int]:
    set_tenant_context(db, tenant_id)
    base = select(BillingInvoice).where(BillingInvoice.tenant_id == tenant_id)
    if status_filter:
        base = base.where(BillingInvoice.status == status_filter)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        base.order_by(BillingInvoice.created_at.desc(), BillingInvoice.invoice_id)
        .offset(page.offset)
        .limit(page.page_size)
    )
    return list(rows.scalars()), total


def get_invoice(db: Session, tenant_id: uuid.UUID, invoice_id: uuid.UUID) -> BillingInvoice:
    set_tenant_context(db, tenant_id)
    return _get_invoice_in_tenant(db, tenant_id, invoice_id)


def list_invoice_lines(db: Session, invoice: BillingInvoice) -> list[BillingInvoiceLine]:
    rows = db.execute(
        select(BillingInvoiceLine)
        .where(BillingInvoiceLine.invoice_id == invoice.invoice_id)
        .order_by(BillingInvoiceLine.line_number)
    )
    return list(rows.scalars())


def issue_invoice(
    auth: Authorized, tenant_id: uuid.UUID, invoice_id: uuid.UUID, expected_version: int
) -> BillingInvoice:
    """DRAFT → ISSUED : la facture est figée et son numéro devient opposable (document interne)."""
    db = auth.db
    set_tenant_context(db, tenant_id)
    invoice = _get_invoice_in_tenant(db, tenant_id, invoice_id)
    check_version(expected_version, invoice.row_version)
    if invoice.status != "DRAFT":
        raise AppError("STATE_TRANSITION_INVALID")
    invoice.status = "ISSUED"
    invoice.issued_at = auth.clock.now()
    invoice.updated_by = auth.user_id
    db.flush()
    record(
        db,
        tenant_id=tenant_id,
        action="billing.invoice.issue",
        entity_type="billing_invoice",
        entity_id=invoice.invoice_id,
        actor_user_id=auth.user_id,
        before={"status": "DRAFT"},
        after={"status": "ISSUED", "total_gnf": invoice.total_gnf},
        changed_fields=["status", "issued_at"],
    )
    db.commit()
    return invoice


def void_invoice(
    auth: Authorized,
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    expected_version: int,
    reason: str,
) -> BillingInvoice:
    """DRAFT/ISSUED → VOIDED (terminal) : annulation motivée, document conservé pour l'audit."""
    db = auth.db
    set_tenant_context(db, tenant_id)
    invoice = _get_invoice_in_tenant(db, tenant_id, invoice_id)
    check_version(expected_version, invoice.row_version)
    if invoice.status == "VOIDED":
        raise AppError("STATE_TRANSITION_INVALID")
    previous_status = invoice.status
    invoice.status = "VOIDED"
    invoice.voided_at = auth.clock.now()
    invoice.void_reason = reason
    invoice.updated_by = auth.user_id
    db.flush()
    record(
        db,
        tenant_id=tenant_id,
        action="billing.invoice.void",
        entity_type="billing_invoice",
        entity_id=invoice.invoice_id,
        actor_user_id=auth.user_id,
        reason=reason,
        before={"status": previous_status},
        after={"status": "VOIDED"},
        changed_fields=["status", "voided_at"],
    )
    db.commit()
    return invoice
