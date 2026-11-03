"""Dernier entretien connu (point de départ des plans) : déclaré par l'atelier, décidé par un tiers.

Permission `maintenance.preventive.manage` pour déclarer et décider, `maintenance.preventive.read` pour
lire ; portée site vérifiée avant tout accès, RLS en seconde barrière. Déclaration, décision et audit sont
validés dans une même transaction. Le déclarant ne peut pas approuver (contrainte en base
`ck_msd_four_eyes` en plus du contrôle applicatif).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.fleet.models import Vehicle
from app.maintenance.preventive import ServiceRule, evaluate_due
from app.maintenance.preventive_baseline_read import load_verified_service_baseline
from app.maintenance.preventive_meters_since import meters_since_anchor
from app.maintenance.preventive_models import MaintenancePlan, ServiceDeclaration
from app.maintenance.preventive_plan_inputs import ServiceDeclarationCreate, ServiceDeclarationDecide
from app.maintenance.preventive_schemas import PreventivePlanStatusOut

MANAGE = "maintenance.preventive.manage"
READ = "maintenance.preventive.read"


def _vehicle_in_scope(auth: Authorized, vehicle_id: uuid.UUID) -> Vehicle:
    vehicle = auth.db.execute(
        select(Vehicle).where(Vehicle.tenant_id == auth.tenant_id, Vehicle.vehicle_id == vehicle_id)
    ).scalar_one_or_none()
    if vehicle is None or not auth.scope.covers_site(vehicle.site_id):
        raise AppError("NOT_FOUND")
    return vehicle


def declare(auth: Authorized, body: ServiceDeclarationCreate) -> ServiceDeclaration:
    if auth.scope.permission != MANAGE:
        raise AppError("PERMISSION_DENIED")
    vehicle = _vehicle_in_scope(auth, body.vehicle_id)
    plan = auth.db.execute(
        select(MaintenancePlan.maintenance_plan_id).where(
            MaintenancePlan.tenant_id == auth.tenant_id,
            MaintenancePlan.vehicle_id == vehicle.vehicle_id,
            MaintenancePlan.code == body.plan_code,
            MaintenancePlan.active.is_(True),
        )
    ).first()
    if plan is None:
        raise AppError("REFERENCE_NOT_FOUND", details={"plan_code": body.plan_code})
    now = auth.clock.now()
    if body.serviced_at is not None and body.serviced_at > now:
        raise AppError("VALIDATION_ERROR", details={"serviced_at": "date future"})
    declaration = ServiceDeclaration(
        tenant_id=auth.tenant_id,
        vehicle_id=vehicle.vehicle_id,
        site_id=vehicle.site_id,
        plan_code=body.plan_code,
        knowledge=body.knowledge,
        serviced_at=body.serviced_at,
        odometer_km=body.odometer_km,
        hour_meter=body.hour_meter,
        note=(body.note or "").strip() or None,
        declared_by=auth.user_id,
        declared_at=now,
    )
    auth.db.add(declaration)
    try:
        auth.db.flush()
    except IntegrityError as exc:
        auth.db.rollback()
        if "uq_msd_one_pending" in str(exc.orig):
            raise AppError("PREVENTIVE_DECLARATION_PENDING") from None
        raise
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        site_id=vehicle.site_id,
        action="maintenance.service_declaration.create",
        entity_type="maintenance_service_declaration",
        entity_id=declaration.service_declaration_id,
        after={"plan_code": body.plan_code, "knowledge": body.knowledge},
        changed_fields=("knowledge", "serviced_at", "odometer_km", "hour_meter"),
    )
    auth.db.commit()
    return declaration


def decide(auth: Authorized, declaration_id: uuid.UUID, body: ServiceDeclarationDecide) -> ServiceDeclaration:
    if auth.scope.permission != MANAGE:
        raise AppError("PERMISSION_DENIED")
    declaration = auth.db.execute(
        select(ServiceDeclaration)
        .where(
            ServiceDeclaration.tenant_id == auth.tenant_id,
            ServiceDeclaration.service_declaration_id == declaration_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if declaration is None or not auth.scope.covers_site(declaration.site_id):
        raise AppError("NOT_FOUND")
    if declaration.status != "PENDING":
        raise AppError("STATE_TRANSITION_INVALID")
    if declaration.declared_by == auth.user_id:
        raise AppError("PREVENTIVE_SELF_APPROVAL_FORBIDDEN")
    declaration.status = "APPROVED" if body.decision == "APPROVE" else "REJECTED"
    declaration.decided_by = auth.user_id
    declaration.decided_at = auth.clock.now()
    declaration.decision_note = (body.note or "").strip() or None
    auth.db.flush()
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        site_id=declaration.site_id,
        action="maintenance.service_declaration.decide",
        entity_type="maintenance_service_declaration",
        entity_id=declaration.service_declaration_id,
        before={"status": "PENDING"},
        after={"status": declaration.status},
        reason=declaration.decision_note,
        changed_fields=("status", "decided_by", "decided_at"),
    )
    auth.db.commit()
    return declaration


def declarations_for_vehicle(auth: Authorized, vehicle_id: uuid.UUID) -> list[ServiceDeclaration]:
    _vehicle_in_scope(auth, vehicle_id)
    return list(
        auth.db.execute(
            select(ServiceDeclaration)
            .where(
                ServiceDeclaration.tenant_id == auth.tenant_id, ServiceDeclaration.vehicle_id == vehicle_id
            )
            .order_by(ServiceDeclaration.declared_at.desc(), ServiceDeclaration.service_declaration_id.desc())
        ).scalars()
    )


def plan_statuses(auth: Authorized, vehicle_id: uuid.UUID) -> list[PreventivePlanStatusOut]:
    """État calculé de chaque plan actif de l'engin, sans rien enregistrer (lecture)."""
    _vehicle_in_scope(auth, vehicle_id)
    now = auth.clock.now()
    plans = auth.db.execute(
        select(MaintenancePlan)
        .where(
            MaintenancePlan.tenant_id == auth.tenant_id,
            MaintenancePlan.vehicle_id == vehicle_id,
            MaintenancePlan.active.is_(True),
        )
        .order_by(MaintenancePlan.code)
    ).scalars()
    out: list[PreventivePlanStatusOut] = []
    for plan in plans:
        baseline = load_verified_service_baseline(
            auth.db, auth.tenant_id, vehicle_id, plan_code=plan.code, as_of=now
        )
        meters = meters_since_anchor(
            auth.db,
            auth.tenant_id,
            vehicle_id,
            anchor_at=baseline.anchor_at,
            anchor_km=baseline.cumulative_km,
            anchor_hours=baseline.cumulative_hours,
            as_of=now,
        )
        rule = ServiceRule(
            km_interval=plan.km_interval, hours_interval=plan.hours_interval, days_interval=plan.days_interval
        )
        result = evaluate_due(rule, baseline, meters, now.date())
        out.append(
            PreventivePlanStatusOut(
                maintenance_plan_id=plan.maintenance_plan_id,
                code=plan.code,
                status=result.status,
                due_triggers=list(result.due_triggers),
                unknown_triggers=list(result.unknown_triggers),
                baseline_source=baseline.source,
                serviced_on=baseline.serviced_on,
                due_on=result.due_on,
                current_km=meters.cumulative_km,
                current_hours=meters.cumulative_hours,
                remaining_km=result.remaining_km,
                remaining_hours=result.remaining_hours,
                km_reliable=meters.km_reliable,
                hours_reliable=meters.hours_reliable,
            )
        )
    return out
