"""Enregistrer un cumul approuvé sur un entretien préventif clôturé.

Service interne transactionnel : l'appelant conserve la responsabilité du commit.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.fleet.models import VehicleMeterReading
from app.maintenance.models import WorkOrder
from app.maintenance.preventive_models import (
    MaintenanceDue,
    MeterReconciliationApproval,
    ServiceMeterBaseline,
)

MANAGE_PERMISSION = "maintenance.preventive.manage"
METER_KINDS = {"ODOMETER_KM", "HOUR_METER"}
MAX_TOTAL = Decimal("100000000")


def _existing_approval_id(
    auth: Authorized,
    work_order_id: uuid.UUID,
    meter_kind: str,
) -> uuid.UUID | None:
    return auth.db.scalar(
        select(ServiceMeterBaseline.reconciliation_approval_id).where(
            ServiceMeterBaseline.tenant_id == auth.tenant_id,
            ServiceMeterBaseline.work_order_id == work_order_id,
            ServiceMeterBaseline.meter_kind == meter_kind,
        )
    )


def record_service_meter_baseline(
    auth: Authorized,
    work_order_id: uuid.UUID,
    meter_kind: str,
    approval_id: uuid.UUID,
    *,
    as_of: datetime,
) -> bool:
    """Figer le cumul de clôture s'il est approuvé et encore actuel.

    Retourne True si la preuve est créée et False lors d'un rejeu identique.
    Une preuve différente pour le même OT et compteur est refusée.
    """
    if auth.scope.permission != MANAGE_PERMISSION:
        raise AppError("PERMISSION_DENIED")
    if as_of.tzinfo is None or as_of.utcoffset() is None or meter_kind not in METER_KINDS:
        raise AppError("STATE_TRANSITION_INVALID")

    order = auth.db.execute(
        select(WorkOrder)
        .where(
            WorkOrder.tenant_id == auth.tenant_id,
            WorkOrder.work_order_id == work_order_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if order is None or not auth.scope.covers_site(order.site_id):
        raise AppError("NOT_FOUND")
    if (
        order.kind != "PREVENTIVE"
        or order.status != "CLOSED"
        or order.closed_at is None
        or order.closed_at > as_of
    ):
        raise AppError("STATE_TRANSITION_INVALID")

    due = auth.db.execute(
        select(MaintenanceDue).where(
            MaintenanceDue.tenant_id == auth.tenant_id,
            MaintenanceDue.work_order_id == order.work_order_id,
            MaintenanceDue.vehicle_id == order.vehicle_id,
        )
    ).scalar_one_or_none()
    if due is None or due.status not in {"SCHEDULED", "COMPLETED"}:
        raise AppError("STATE_TRANSITION_INVALID")

    approval = auth.db.execute(
        select(MeterReconciliationApproval).where(
            MeterReconciliationApproval.tenant_id == auth.tenant_id,
            MeterReconciliationApproval.approval_id == approval_id,
            MeterReconciliationApproval.vehicle_id == order.vehicle_id,
            MeterReconciliationApproval.site_id == order.site_id,
            MeterReconciliationApproval.meter_kind == meter_kind,
        )
    ).scalar_one_or_none()
    if (
        approval is None
        or approval.approved_at > order.closed_at
        or not approval.current_total.is_finite()
        or approval.current_total < 0
        or approval.current_total >= MAX_TOTAL
    ):
        raise AppError("STATE_TRANSITION_INVALID")

    newer_reading = auth.db.scalar(
        select(VehicleMeterReading.vehicle_meter_reading_id)
        .where(
            VehicleMeterReading.tenant_id == auth.tenant_id,
            VehicleMeterReading.vehicle_id == order.vehicle_id,
            VehicleMeterReading.meter_kind == meter_kind,
            VehicleMeterReading.read_at > approval.approved_at,
            VehicleMeterReading.read_at <= order.closed_at,
        )
        .limit(1)
    )
    if newer_reading is not None:
        raise AppError("STATE_TRANSITION_INVALID")

    existing_approval_id = _existing_approval_id(auth, work_order_id, meter_kind)
    if existing_approval_id is not None:
        if existing_approval_id != approval_id:
            raise AppError("STATE_TRANSITION_INVALID")
        return False

    statement = (
        insert(ServiceMeterBaseline)
        .values(
            tenant_id=auth.tenant_id,
            maintenance_plan_id=due.maintenance_plan_id,
            maintenance_due_id=due.maintenance_due_id,
            work_order_id=order.work_order_id,
            vehicle_id=order.vehicle_id,
            site_id=order.site_id,
            meter_kind=meter_kind,
            cumulative_total=approval.current_total,
            reconciliation_approval_id=approval.approval_id,
            serviced_at=order.closed_at,
            recorded_by=auth.user_id,
        )
        .on_conflict_do_nothing(constraint="uq_msmb_work_order_kind")
        .returning(ServiceMeterBaseline.service_meter_baseline_id)
    )
    inserted_id = auth.db.execute(statement).scalar_one_or_none()
    if inserted_id is None:
        if _existing_approval_id(auth, work_order_id, meter_kind) != approval_id:
            raise AppError("STATE_TRANSITION_INVALID")
        return False

    record(
        auth.db,
        tenant_id=auth.tenant_id,
        site_id=order.site_id,
        actor_user_id=auth.user_id,
        action="maintenance.service_meter_baseline.create",
        entity_type="maintenance_service_meter_baseline",
        entity_id=inserted_id,
        changed_fields=(
            "meter_kind",
            "cumulative_total",
            "reconciliation_approval_id",
        ),
    )
    return True
