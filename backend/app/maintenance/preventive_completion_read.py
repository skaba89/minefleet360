"""Preuves disponibles pour la finalisation d'un entretien préventif.

Lecture bornée, tenant/site explicites ; la commande de finalisation reste
l'autorité et revérifie les preuves dans sa transaction d'écriture.
"""

import uuid
from typing import Literal

from sqlalchemy import select

from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.fleet.models import VehicleMeterReading
from app.maintenance.models import WorkOrder
from app.maintenance.preventive_models import (
    MaintenanceDue,
    MaintenancePlan,
    MeterReconciliationApproval,
    ServiceMeterBaseline,
)
from app.maintenance.preventive_schemas import (
    PreventiveApprovalChoiceOut,
    PreventiveCompletionContextOut,
    PreventiveCompletionMeterOut,
)

CHOICE_LIMIT = 25


def preventive_completion_context(
    auth: Authorized, work_order_id: uuid.UUID
) -> PreventiveCompletionContextOut:
    if auth.scope.permission != "maintenance.preventive.manage":
        raise AppError("PERMISSION_DENIED")
    order = auth.db.scalar(
        select(WorkOrder).where(
            WorkOrder.tenant_id == auth.tenant_id,
            WorkOrder.work_order_id == work_order_id,
        )
    )
    if order is None or not auth.scope.covers_site(order.site_id):
        raise AppError("NOT_FOUND")
    if order.kind != "PREVENTIVE" or order.status != "CLOSED" or order.closed_at is None:
        raise AppError(
            "STATE_TRANSITION_INVALID", message_fr="Clôturez l'OT préventif avant sa finalisation."
        )
    due = auth.db.scalar(
        select(MaintenanceDue).where(
            MaintenanceDue.tenant_id == auth.tenant_id,
            MaintenanceDue.work_order_id == order.work_order_id,
            MaintenanceDue.vehicle_id == order.vehicle_id,
        )
    )
    if due is None or due.status not in {"SCHEDULED", "COMPLETED"}:
        raise AppError("STATE_TRANSITION_INVALID")
    plan = auth.db.scalar(
        select(MaintenancePlan).where(
            MaintenancePlan.tenant_id == auth.tenant_id,
            MaintenancePlan.maintenance_plan_id == due.maintenance_plan_id,
            MaintenancePlan.vehicle_id == order.vehicle_id,
        )
    )
    if plan is None:
        raise AppError("STATE_TRANSITION_INVALID")
    frozen = {
        row.meter_kind: row.cumulative_total
        for row in auth.db.scalars(
            select(ServiceMeterBaseline).where(
                ServiceMeterBaseline.tenant_id == auth.tenant_id,
                ServiceMeterBaseline.site_id == order.site_id,
                ServiceMeterBaseline.work_order_id == order.work_order_id,
                ServiceMeterBaseline.maintenance_due_id == due.maintenance_due_id,
                ServiceMeterBaseline.maintenance_plan_id == plan.maintenance_plan_id,
                ServiceMeterBaseline.vehicle_id == order.vehicle_id,
                ServiceMeterBaseline.serviced_at == order.closed_at,
            )
        )
    }
    meters: list[PreventiveCompletionMeterOut] = []
    required_kinds: list[Literal["ODOMETER_KM", "HOUR_METER"]] = []
    if plan.km_interval is not None:
        required_kinds.append("ODOMETER_KM")
    if plan.hours_interval is not None:
        required_kinds.append("HOUR_METER")
    for kind in required_kinds:
        choices: list[MeterReconciliationApproval]
        if kind in frozen or due.status == "COMPLETED":
            choices = []
        else:
            newer_reading = select(VehicleMeterReading.vehicle_meter_reading_id).where(
                VehicleMeterReading.tenant_id == auth.tenant_id,
                VehicleMeterReading.vehicle_id == order.vehicle_id,
                VehicleMeterReading.meter_kind == kind,
                VehicleMeterReading.read_at > MeterReconciliationApproval.approved_at,
                VehicleMeterReading.read_at <= order.closed_at,
            )
            choices = list(
                auth.db.scalars(
                    select(MeterReconciliationApproval)
                    .where(
                        MeterReconciliationApproval.tenant_id == auth.tenant_id,
                        MeterReconciliationApproval.vehicle_id == order.vehicle_id,
                        MeterReconciliationApproval.site_id == order.site_id,
                        MeterReconciliationApproval.meter_kind == kind,
                        MeterReconciliationApproval.approved_at <= order.closed_at,
                        MeterReconciliationApproval.current_total >= 0,
                        MeterReconciliationApproval.current_total < 100000000,
                        ~newer_reading.exists(),
                    )
                    .order_by(
                        MeterReconciliationApproval.approved_at.desc(),
                        MeterReconciliationApproval.approval_id.desc(),
                    )
                    .limit(CHOICE_LIMIT)
                )
            )
        meters.append(
            PreventiveCompletionMeterOut(
                meter_kind=kind,
                frozen_total=frozen.get(kind),
                approvals=[
                    PreventiveApprovalChoiceOut(
                        approval_id=approval.approval_id,
                        cumulative_total=approval.current_total,
                        approved_at=approval.approved_at,
                    )
                    for approval in choices
                ],
            )
        )
    return PreventiveCompletionContextOut(
        maintenance_due_id=due.maintenance_due_id,
        status="COMPLETED" if due.status == "COMPLETED" else "SCHEDULED",
        plan_code=plan.code,
        closed_at=order.closed_at,
        meters=meters,
    )
