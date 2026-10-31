"""Lecture financière : données historiques inconnues et séparation des devises."""

import uuid
from decimal import Decimal
from unittest.mock import Mock

import pytest

from app.maintenance.parts_cost_reader import load_work_order_parts_cost


def test_reader_preserves_unknown_historical_costs() -> None:
    db = Mock()
    db.execute.return_value.all.return_value = [
        (None, None),
        (Decimal("12.500000"), "GNF"),
    ]
    result, currency = load_work_order_parts_cost(
        db, tenant_id=uuid.uuid4(), site_id=uuid.uuid4(), work_order_id=uuid.uuid4()
    )
    assert result.known_total == Decimal("12.500000")
    assert result.valued_movements == 1
    assert result.unvalued_movements == 1
    assert not result.complete
    assert currency == "GNF"


def test_reader_rejects_mixed_currencies() -> None:
    db = Mock()
    db.execute.return_value.all.return_value = [
        (Decimal("10"), "GNF"),
        (Decimal("10"), "EUR"),
    ]
    with pytest.raises(ValueError, match="devises"):
        load_work_order_parts_cost(
            db, tenant_id=uuid.uuid4(), site_id=uuid.uuid4(), work_order_id=uuid.uuid4()
        )


def test_empty_order_no_currency() -> None:
    db = Mock()
    db.execute.return_value.all.return_value = []
    result, currency = load_work_order_parts_cost(
        db, tenant_id=uuid.uuid4(), site_id=uuid.uuid4(), work_order_id=uuid.uuid4()
    )
    assert result.complete
    assert result.known_total == 0
    assert currency is None
