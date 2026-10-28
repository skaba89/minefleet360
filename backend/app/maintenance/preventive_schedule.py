"""Rattachement transactionnel d'une échéance existante à un OT préventif.

Service interne ; pas de route ni de planificateur. RLS tenant obligatoire.
"""

import uuid

from sqlalchemy import select

from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.fleet.models import Vehicle
from app.maintenance.models import WorkOrder
from app.maintenance.preventive_models import MaintenanceDue, MaintenancePlan
from app.maintenance.schemas import WorkOrderCreate
from app.maintenance.service import _create_work_order_uncommitted


def schedule_preventive_order(auth: Authorized, due_id: uuid.UUID) -> uuid.UUID:
    """Une échéance donne au plus un OT, dans une seule transaction."""
    if auth.scope.permission != "maintenance.preventive.manage":
        raise AppError("PERMISSION_DENIED")

    due = auth.db.execute(
        select(MaintenanceDue)
        .where(
            MaintenanceDue.tenant_id == auth.tenant_id,
            MaintenanceDue.maintenance_due_id == due_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if due is None:
        raise AppError("NOT_FOUND")
    vehicle = auth.db.execute(
        select(Vehicle).where(
            Vehicle.tenant_id == auth.tenant_id,
            Vehicle.vehicle_id == due.vehicle_id,
        )
    ).scalar_one_or_none()
    if vehicle is None or not auth.scope.covers_site(vehicle.site_id):
        raise AppError("NOT_FOUND")
    if due.work_order_id is not None:
        return due.work_order_id
    if due.status != "DUE":
        raise AppError("STATE_TRANSITION_INVALID")

    plan = auth.db.execute(
        select(MaintenancePlan).where(
            MaintenancePlan.tenant_id == auth.tenant_id,
            MaintenancePlan.maintenance_plan_id == due.maintenance_plan_id,
            MaintenancePlan.vehicle_id == due.vehicle_id,
        )
    ).scalar_one_or_none()
    if plan is None or not plan.active:
        raise AppError("STATE_TRANSITION_INVALID")

    # Le noyau OT contrôle lui-même la portée site et verrouille le véhicule.
    out = _create_work_order_uncommitted(
        auth,
        WorkOrderCreate(
            vehicle_id=due.vehicle_id,
            symptom_code="SERVICE",
            priority="NORMAL",
            description="Entretien préventif programmé",
            immobilize=False,
        ),
    )
    order = auth.db.execute(
        select(WorkOrder).where(
            WorkOrder.tenant_id == auth.tenant_id,
            WorkOrder.work_order_id == out.work_order_id,
        )
    ).scalar_one()
    order.kind = "PREVENTIVE"
    due.work_order_id = order.work_order_id
    due.status = "SCHEDULED"
    auth.db.flush()
    order_id = order.work_order_id
    auth.db.commit()
    return order_id
