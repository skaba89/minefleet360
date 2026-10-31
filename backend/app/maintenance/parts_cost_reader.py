"""Lecture des coûts historiques de pièces consommées, limitée au tenant et au site."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.maintenance.parts_costs import WorkOrderPartsCost, aggregate_parts_cost
from app.maintenance.parts_models import SparePartMovement


def load_work_order_parts_cost(
    db: Session, *, tenant_id: uuid.UUID, site_id: uuid.UUID, work_order_id: uuid.UUID
) -> tuple[WorkOrderPartsCost, str | None]:
    """Renvoie (coût connu, devise) ; complete=False si une consommation n'est pas valorisée.

    Ne lit que les sorties explicitement liées à cet OT. Les historiques sans lien
    ne sont pas attribués arbitrairement à un ordre de travail.
    """
    stmt = select(
        SparePartMovement.total_cost,
        SparePartMovement.valuation_currency,
    ).where(
        SparePartMovement.tenant_id == tenant_id,
        SparePartMovement.site_id == site_id,
        SparePartMovement.work_order_id == work_order_id,
        SparePartMovement.movement_type == "ISSUE",
    )
    rows = db.execute(stmt).all()
    currencies = {currency for amount, currency in rows if amount is not None and currency is not None}
    if len(currencies) > 1:
        raise ValueError("Plusieurs devises sans conversion vérifiée")
    result = aggregate_parts_cost(
        [amount for amount, _ in rows],
        currency_count=len(currencies) if currencies else 1,
    )
    return result, next(iter(currencies), None)
