"""Source PostgreSQL du dernier entretien préventif clôturé.

La clôture d'un OT est une preuve datée, mais les relevés bruts ne sont
pas automatiquement des cumuls fiables après remise à zéro du compteur.
"""

import uuid
from datetime import date

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.maintenance.models import WorkOrder
from app.maintenance.preventive import ServiceBaseline


def completed_preventive_orders_query(
    tenant_id: uuid.UUID, vehicle_id: uuid.UUID
) -> Select[WorkOrder]:
    return (
        select(WorkOrder)
        .where(
            WorkOrder.tenant_id == tenant_id,
            WorkOrder.vehicle_id == vehicle_id,
            WorkOrder.kind == "PREVENTIVE",
            WorkOrder.status == "CLOSED",
            WorkOrder.closed_at.is_not(None),
        )
        .order_by(WorkOrder.closed_at.desc(), WorkOrder.work_order_id.desc())
        .limit(1)
    )


def load_verified_service_baseline(
    db: Session, tenant_id: uuid.UUID, vehicle_id: uuid.UUID
) -> ServiceBaseline:
    """Utiliser la clôture d'un OT préventif, jamais un OT correctif.

    Aucune extrapolation de compteur : les cumuls nécessitent une source
    explicitement qualifiée, non encore branchée ici.
    """
    order = db.scalars(completed_preventive_orders_query(tenant_id, vehicle_id)).first()
    serviced_on: date | None = order.closed_at.date() if order and order.closed_at else None
    return ServiceBaseline(serviced_on=serviced_on)
