"""Contrat transactionnel : aucune validation implicite ni commit des réceptions valorisées."""

import uuid
from decimal import Decimal
from unittest.mock import Mock

import pytest

from app.maintenance.valued_receipts import record_valued_receipt


def _arguments() -> dict[str, object]:
    return {
        "tenant_id": uuid.uuid4(),
        "site_id": uuid.uuid4(),
        "store_id": uuid.uuid4(),
        "part_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "quantity": Decimal("3"),
        "unit_cost": Decimal("125"),
        "currency": "GNF",
        "reference": "FACTURE-123",
    }


def test_receipt_uses_single_transaction_and_historical_price() -> None:
    db = Mock()
    db.execute.return_value.first.return_value = (uuid.uuid4(),)
    movement = record_valued_receipt(db, **_arguments())
    assert movement.total_cost == Decimal("375")
    assert movement.unit_cost == Decimal("125")
    assert movement.valuation_currency == "GNF"
    assert movement.movement_type == "RECEIPT"
    db.add.assert_called_once_with(movement)
    db.flush.assert_called_once()
    db.commit.assert_not_called()


def test_missing_opening_valuation_refuses_stock_update() -> None:
    db = Mock()
    db.execute.return_value.first.return_value = None
    with pytest.raises(ValueError, match="historique"):
        record_valued_receipt(db, **_arguments())
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_invalid_currency_never_writes() -> None:
    db = Mock()
    with pytest.raises(ValueError):
        record_valued_receipt(db, **{**_arguments(), "currency": "gnf"})
    db.execute.assert_not_called()
