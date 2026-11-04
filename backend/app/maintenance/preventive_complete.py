"""Finaliser une échéance préventive depuis un OT clôturé et ses preuves.

Service interne transactionnel : il fige les cumuls fournis, termine
l'échéance et valide l'ensemble dans un seul commit.
"""

import uuid
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.maintenance.models import WorkOrder
from app.maintenance.preventive_closure_meters import closure_totals
from app.maintenance.preventive_models import (
    MaintenanceDue,
    MaintenancePlan,
    ServiceMeterBaseline,
)
from app.maintenance.preventive_service_baseline_persist import (
    MAX_TOTAL,
    METER_KINDS,
    record_computed_meter_baseline,
    record_service_meter_baseline,
)

MANAGE_PERMISSION = "maintenance.preventive.manage"


def _required_meter_kinds(plan: MaintenancePlan) -> set[str]:
    required: set[str] = set()
    if plan.km_interval is not None:
        required.add("ODOMETER_KM")
    if plan.hours_interval is not None:
        required.add("HOUR_METER")
    return required


def complete_preventive_due(
    auth: Authorized,
    work_order_id: uuid.UUID,
    approval_ids: Mapping[str, uuid.UUID],
    *,
    as_of: datetime,
) -> bool:
    """Terminer l'échéance avec toutes les preuves exigées par le plan.

    Retourne True lors de la transition vers COMPLETED et False pour un
    rejeu identique. Une approbation différente ou une preuve manquante
    invalide toute la transaction.
    """
    if auth.scope.permission != MANAGE_PERMISSION:
        raise AppError("PERMISSION_DENIED")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise AppError("STATE_TRANSITION_INVALID")

    requested = dict(approval_ids)
    invalid_kinds = set(requested) - METER_KINDS
    if invalid_kinds:
        raise AppError(
            "STATE_TRANSITION_INVALID",
            details={"invalid_meter_kinds": sorted(invalid_kinds)},
        )

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
        select(MaintenanceDue)
        .where(
            MaintenanceDue.tenant_id == auth.tenant_id,
            MaintenanceDue.work_order_id == order.work_order_id,
            MaintenanceDue.vehicle_id == order.vehicle_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if due is None or due.status not in {"SCHEDULED", "COMPLETED"}:
        raise AppError("STATE_TRANSITION_INVALID")

    plan = auth.db.execute(
        select(MaintenancePlan).where(
            MaintenancePlan.tenant_id == auth.tenant_id,
            MaintenancePlan.maintenance_plan_id == due.maintenance_plan_id,
            MaintenancePlan.vehicle_id == order.vehicle_id,
        )
    ).scalar_one_or_none()
    if plan is None:
        raise AppError("STATE_TRANSITION_INVALID")

    existing: dict[str, uuid.UUID | None] = {
        meter_kind: approval_id
        for meter_kind, approval_id in auth.db.execute(
            select(
                ServiceMeterBaseline.meter_kind,
                ServiceMeterBaseline.reconciliation_approval_id,
            ).where(
                ServiceMeterBaseline.tenant_id == auth.tenant_id,
                ServiceMeterBaseline.maintenance_plan_id == plan.maintenance_plan_id,
                ServiceMeterBaseline.maintenance_due_id == due.maintenance_due_id,
                ServiceMeterBaseline.work_order_id == order.work_order_id,
                ServiceMeterBaseline.vehicle_id == order.vehicle_id,
                ServiceMeterBaseline.serviced_at == order.closed_at,
            )
        ).all()
    }
    conflicting_kinds = {
        kind for kind, approval_id in requested.items() if kind in existing and existing[kind] != approval_id
    }
    if conflicting_kinds:
        raise AppError(
            "STATE_TRANSITION_INVALID",
            details={"conflicting_meter_kinds": sorted(conflicting_kinds)},
        )

    effective_kinds = existing.keys() | requested.keys()
    missing_kinds = _required_meter_kinds(plan) - effective_kinds
    computed: dict[str, Decimal] = {}
    if missing_kinds and due.status != "COMPLETED":
        # Sans approbation fournie : cumul calculé depuis le jalon précédent et les relevés (0059).
        totals = closure_totals(auth.db, auth.tenant_id, order.vehicle_id, plan.code, order.closed_at)
        for kind in sorted(missing_kinds):
            value = totals.get(kind)
            if value is not None and value.is_finite() and Decimal(0) <= value < MAX_TOTAL:
                computed[kind] = value
        missing_kinds -= computed.keys()
    if missing_kinds:
        raise AppError(
            "STATE_TRANSITION_INVALID",
            message_fr="Aucun relevé de compteur avant la clôture : enregistrez un relevé pour finaliser.",
            details={"missing_meter_kinds": sorted(missing_kinds)},
        )

    if due.status == "COMPLETED":
        unrecorded_kinds = requested.keys() - existing.keys()
        if unrecorded_kinds:
            raise AppError(
                "STATE_TRANSITION_INVALID",
                details={"unrecorded_meter_kinds": sorted(unrecorded_kinds)},
            )
        auth.db.commit()
        return False

    for meter_kind in sorted(requested):
        record_service_meter_baseline(
            auth,
            order.work_order_id,
            meter_kind,
            requested[meter_kind],
            as_of=as_of,
        )

    for meter_kind, total in computed.items():
        record_computed_meter_baseline(auth, order, due, meter_kind, total)

    due.status = "COMPLETED"
    auth.db.flush()
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        site_id=order.site_id,
        actor_user_id=auth.user_id,
        action="maintenance.preventive_due.complete",
        entity_type="maintenance_due",
        entity_id=due.maintenance_due_id,
        before={"status": "SCHEDULED"},
        after={"status": due.status},
        changed_fields=("status",),
    )
    auth.db.commit()
    return True
