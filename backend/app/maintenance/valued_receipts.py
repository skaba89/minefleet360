"""Écriture atomique d'une réception valorisée, à utiliser dans une transaction API.

Ne commit pas : l'appelant commit le solde et le mouvement ensemble.
Les anciennes API de mouvements ne sont pas encore raccordées à ce service.
"""

import uuid
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.maintenance.parts_models import SparePartMovement
from app.maintenance.receipt_valuation import prepare_valued_receipt


def record_valued_receipt(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    store_id: uuid.UUID,
    part_id: uuid.UUID,
    user_id: uuid.UUID,
    quantity: Decimal,
    unit_cost: Decimal,
    currency: str,
    reference: str,
) -> SparePartMovement:
    """Inscrit solde et journal dans la transaction courante, sans commit.

    L'UPSERT PostgreSQL verrouille la ligne cible et refuse une valeur
    d'ouverture inconnue ou une devise différente (race-safe).
    """
    prepare_valued_receipt(
        on_hand=Decimal("0"),
        stock_value=None,
        existing_currency=None,
        quantity=quantity,
        unit_cost=unit_cost,
        currency=currency,
    )
    total = quantity * unit_cost
    row = db.execute(
        text(
            "INSERT INTO spare_part_balance "
            "(tenant_id, site_id, spare_part_store_id, spare_part_id, "
            "on_hand, stock_value, valuation_currency) "
            "VALUES (:tenant_id, :site_id, :store_id, :part_id, "
            ":quantity, :value, :currency) "
            "ON CONFLICT (tenant_id, spare_part_store_id, spare_part_id) "
            "DO UPDATE SET on_hand = spare_part_balance.on_hand + EXCLUDED.on_hand, "
            "stock_value = COALESCE(spare_part_balance.stock_value, 0) + EXCLUDED.stock_value, "
            "valuation_currency = EXCLUDED.valuation_currency "
            "WHERE (spare_part_balance.stock_value IS NOT NULL "
            "AND spare_part_balance.valuation_currency = EXCLUDED.valuation_currency) "
            "OR (spare_part_balance.on_hand = 0 "
            "AND spare_part_balance.stock_value IS NULL "
            "AND spare_part_balance.valuation_currency IS NULL) "
            "RETURNING spare_part_balance_id"
        ),
        {
            "tenant_id": tenant_id,
            "site_id": site_id,
            "store_id": store_id,
            "part_id": part_id,
            "quantity": quantity,
            "value": total,
            "currency": currency,
        },
    ).first()
    if row is None:
        raise ValueError("Stock historique sans valeur ou devise incompatible")
    movement = SparePartMovement(
        tenant_id=tenant_id,
        site_id=site_id,
        spare_part_store_id=store_id,
        spare_part_id=part_id,
        movement_type="RECEIPT",
        quantity=quantity,
        unit_cost=unit_cost,
        total_cost=total,
        valuation_currency=currency,
        reference=reference,
        recorded_by=user_id,
    )
    db.add(movement)
    db.flush()
    return movement
