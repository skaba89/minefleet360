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


def load_verified_service_baseline(
    db: Session,
    tenant_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    *,
    plan_code: str | None = None,
    as_of: datetime | None = None,
) -> ServiceBaseline:
    """Utiliser la clôture et les cumuls approuvés du même entretien.

    Le code du plan conserve la continuité entre ses versions. Une
    prévisualisation historique ignore les clôtures postérieures à as_of.
    Aucune extrapolation de compteur n'est effectuée.
    """
    order = db.scalars(
        completed_preventive_orders_query(
            tenant_id,
            vehicle_id,
            plan_code=plan_code,
            as_of=as_of,
        )
    ).first()
    if order is None or order.closed_at is None:
        return ServiceBaseline()

    serviced_on: date = order.closed_at.date()
    work_order_id: uuid.UUID | None = getattr(order, "work_order_id", None)
    if work_order_id is None:
        return ServiceBaseline(serviced_on=serviced_on)

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
    )
