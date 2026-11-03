"""Source PostgreSQL du dernier entretien préventif clôturé.

La clôture d'un OT est une preuve datée, mais les relevés bruts ne sont
pas automatiquement des cumuls fiables après remise à zéro du compteur.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.maintenance.models import WorkOrder
from app.maintenance.preventive import ServiceBaseline
from app.maintenance.preventive_models import (
    MaintenanceDue,
    MaintenancePlan,
    ServiceDeclaration,
    ServiceMeterBaseline,
)


def completed_preventive_orders_query(
    tenant_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    *,
    plan_code: str | None = None,
    as_of: datetime | None = None,
) -> Select[WorkOrder]:
    query = select(WorkOrder)
    if plan_code is not None:
        query = query.join(
            MaintenanceDue,
            (MaintenanceDue.tenant_id == WorkOrder.tenant_id)
            & (MaintenanceDue.work_order_id == WorkOrder.work_order_id),
        ).join(
            MaintenancePlan,
            (MaintenancePlan.tenant_id == MaintenanceDue.tenant_id)
            & (MaintenancePlan.maintenance_plan_id == MaintenanceDue.maintenance_plan_id),
        )

    query = query.where(
        WorkOrder.tenant_id == tenant_id,
        WorkOrder.vehicle_id == vehicle_id,
        WorkOrder.kind == "PREVENTIVE",
        WorkOrder.status == "CLOSED",
        WorkOrder.closed_at.is_not(None),
    )
    if plan_code is not None:
        query = query.where(
            MaintenanceDue.tenant_id == tenant_id,
            MaintenanceDue.vehicle_id == vehicle_id,
            MaintenancePlan.tenant_id == tenant_id,
            MaintenancePlan.vehicle_id == vehicle_id,
            MaintenancePlan.code == plan_code,
        )
    if as_of is not None:
        query = query.where(WorkOrder.closed_at <= as_of)
    return query.order_by(WorkOrder.closed_at.desc(), WorkOrder.work_order_id.desc()).limit(1)


def _order_baseline(
    db: Session,
    tenant_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    *,
    plan_code: str | None,
    as_of: datetime | None,
) -> ServiceBaseline | None:
    """Jalon issu de la clôture du dernier OT préventif et de ses cumuls approuvés (None sinon)."""
    order = db.scalars(
        completed_preventive_orders_query(
            tenant_id,
            vehicle_id,
            plan_code=plan_code,
            as_of=as_of,
        )
    ).first()
    if order is None or order.closed_at is None:
        return None

    serviced_on: date = order.closed_at.date()
    work_order_id: uuid.UUID | None = getattr(order, "work_order_id", None)
    if work_order_id is None:
        return ServiceBaseline(serviced_on=serviced_on, anchor_at=order.closed_at, source="WORK_ORDER")

    meter_rows = db.execute(
        select(
            ServiceMeterBaseline.meter_kind,
            ServiceMeterBaseline.cumulative_total,
        ).where(
            ServiceMeterBaseline.tenant_id == tenant_id,
            ServiceMeterBaseline.work_order_id == work_order_id,
            ServiceMeterBaseline.vehicle_id == vehicle_id,
            ServiceMeterBaseline.serviced_at == order.closed_at,
        )
    ).all()
    totals: dict[str, Decimal] = {
        meter_kind: total for meter_kind, total in meter_rows if total.is_finite() and total >= 0
    }
    return ServiceBaseline(
        serviced_on=serviced_on,
        cumulative_km=totals.get("ODOMETER_KM"),
        cumulative_hours=totals.get("HOUR_METER"),
        anchor_at=order.closed_at,
        source="WORK_ORDER",
    )


def _declaration_baseline(
    db: Session,
    tenant_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    *,
    plan_code: str,
    as_of: datetime | None,
) -> tuple[datetime, ServiceBaseline] | None:
    """Dernière déclaration approuvée du dernier entretien, avec l'instant qui la date (None sinon)."""
    query = (
        select(ServiceDeclaration)
        .where(
            ServiceDeclaration.tenant_id == tenant_id,
            ServiceDeclaration.vehicle_id == vehicle_id,
            ServiceDeclaration.plan_code == plan_code,
            ServiceDeclaration.status == "APPROVED",
        )
        .order_by(ServiceDeclaration.decided_at.desc(), ServiceDeclaration.service_declaration_id.desc())
    )
    if as_of is not None:
        query = query.where(ServiceDeclaration.decided_at <= as_of)
    declaration = db.scalars(query.limit(1)).first()
    if declaration is None or declaration.decided_at is None:
        return None
    if declaration.knowledge == "UNKNOWN":
        return declaration.decided_at, ServiceBaseline(
            initial_due_on=declaration.decided_at.date(),
            initial_key=str(declaration.service_declaration_id),
            source="INITIAL_REQUIRED",
        )
    assert declaration.serviced_at is not None
    return declaration.serviced_at, ServiceBaseline(
        serviced_on=declaration.serviced_at.date(),
        cumulative_km=declaration.odometer_km,
        cumulative_hours=declaration.hour_meter,
        anchor_at=declaration.serviced_at,
        source="DECLARATION",
    )


def load_verified_service_baseline(
    db: Session,
    tenant_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    *,
    plan_code: str | None = None,
    as_of: datetime | None = None,
) -> ServiceBaseline:
    """Jalon le plus récent : clôture d'OT préventif ou dernier entretien déclaré et approuvé.

    Le code du plan conserve la continuité entre ses versions. Une
    prévisualisation historique ignore les clôtures et approbations postérieures à as_of.
    Aucune extrapolation de compteur n'est effectuée. Un dernier entretien déclaré inconnu
    n'est remplacé que par un entretien réellement clôturé ensuite (ou une nouvelle déclaration).
    """
    from_order = _order_baseline(db, tenant_id, vehicle_id, plan_code=plan_code, as_of=as_of)
    declared = (
        _declaration_baseline(db, tenant_id, vehicle_id, plan_code=plan_code, as_of=as_of)
        if plan_code is not None
        else None
    )
    if declared is None:
        return from_order or ServiceBaseline()
    declared_at, declared_baseline = declared
    if from_order is not None and from_order.anchor_at is not None and from_order.anchor_at >= declared_at:
        return from_order
    return declared_baseline
