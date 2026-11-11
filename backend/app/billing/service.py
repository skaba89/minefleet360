"""Services du catalogue de plans SaaS (lot 1) — actions réservées à PLATFORM_ADMIN.

Règles clés :
- le code est immuable et unique (409 DUPLICATE_PLAN_CODE) ;
- RETIRED est un état terminal : plus aucune modification (422 PLAN_RETIRED) ;
- toute écriture est journalisée côté plateforme (tenant_id = PLATFORM_TENANT_ID).
L'application effective des quotas aux sociétés arrive avec le lot 2 (abonnements) :
ce lot livre le référentiel, pas l'application des limites.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.billing.models import SaaSPlan
from app.billing.schemas import PlanCreate, PlanUpdate
from app.core.errors import AppError
from app.core.http import PageParams, check_version
from app.core.tenancy import PLATFORM_TENANT_ID

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
