"""Les coûts d'un OT restent partiels lorsque des mouvements ne sont pas valorisés."""

from decimal import Decimal

import pytest

from app.maintenance.parts_costs import aggregate_parts_cost


def test_complete_parts_cost() -> None:
    total = aggregate_parts_cost([Decimal("12.50"), Decimal("7.25")])
    assert total.known_total == Decimal("19.75")
    assert total.valued_movements == 2
    assert total.unvalued_movements == 0
    assert total.complete


def test_historical_unknown_price_is_not_zero() -> None:
    total = aggregate_parts_cost([Decimal("12.50"), None])
    assert total.known_total == Decimal("12.50")
    assert total.unvalued_movements == 1
    assert not total.complete


def test_empty_work_order_is_complete_zero() -> None:
    total = aggregate_parts_cost([])
    assert total.complete
    assert total.known_total == 0


@pytest.mark.parametrize("amount", [Decimal("-1"), Decimal("NaN"), Decimal("Infinity")])
def test_reject_invalid_cost(amount: Decimal) -> None:
    with pytest.raises(ValueError):
        aggregate_parts_cost([amount])


def test_no_mixed_currency_without_conversion() -> None:
    with pytest.raises(ValueError):
        aggregate_parts_cost([Decimal("1")], currency_count=2)
