"""Réceptions valorisées : ne jamais convertir un coût inconnu en zéro."""

from decimal import Decimal

import pytest

from app.maintenance.receipt_valuation import prepare_valued_receipt


def test_new_stock_can_be_valued() -> None:
    result = prepare_valued_receipt(
        on_hand=Decimal("0"),
        stock_value=None,
        existing_currency=None,
        quantity=Decimal("2"),
        unit_cost=Decimal("125"),
        currency="GNF",
    )
    assert result.quantity == 2
    assert result.value == 250


def test_existing_valued_stock_uses_cmp() -> None:
    result = prepare_valued_receipt(
        on_hand=Decimal("3"),
        stock_value=Decimal("300"),
        existing_currency="GNF",
        quantity=Decimal("2"),
        unit_cost=Decimal("150"),
        currency="GNF",
    )
    assert result.quantity == 5
    assert result.value == 600


def test_historical_unvalued_stock_is_rejected() -> None:
    with pytest.raises(ValueError, match="historique"):
        prepare_valued_receipt(
            on_hand=Decimal("3"),
            stock_value=None,
            existing_currency=None,
            quantity=Decimal("2"),
            unit_cost=Decimal("100"),
            currency="GNF",
        )


def test_mixed_currencies_are_rejected() -> None:
    with pytest.raises(ValueError, match="devise"):
        prepare_valued_receipt(
            on_hand=Decimal("3"),
            stock_value=Decimal("300"),
            existing_currency="EUR",
            quantity=Decimal("2"),
            unit_cost=Decimal("100"),
            currency="GNF",
        )


@pytest.mark.parametrize("invalid", [Decimal("NaN"), Decimal("Infinity"), Decimal("-1")])
def test_invalid_prices_are_rejected(invalid: Decimal) -> None:
    with pytest.raises(ValueError):
        prepare_valued_receipt(
            on_hand=Decimal("0"),
            stock_value=None,
            existing_currency=None,
            quantity=Decimal("1"),
            unit_cost=invalid,
            currency="GNF",
        )
