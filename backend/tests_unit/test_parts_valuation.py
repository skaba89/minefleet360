"""Règles de valorisation au CMP : précision et invariants financiers."""

from decimal import Decimal

import pytest

from app.maintenance.valuation import Valuation, issue_cmp, receive_cmp


def test_cmp_multiple_receipts_and_issue_preserve_value() -> None:
    stock = Valuation(Decimal("0"), Decimal("0"))
    stock = receive_cmp(stock, Decimal("3"), Decimal("10.00"))
    stock = receive_cmp(stock, Decimal("2"), Decimal("13.00"))
    assert stock.quantity == Decimal("5")
    assert stock.value == Decimal("56.00")
    stock, cost = issue_cmp(stock, Decimal("2"))
    assert cost == Decimal("22.400000")
    assert stock.quantity == Decimal("3")
    assert stock.value == Decimal("33.600000")
    stock, remainder = issue_cmp(stock, Decimal("3"))
    assert remainder == Decimal("33.600000")
    assert stock == Valuation(Decimal("0"), Decimal("0"))
    assert cost + remainder == Decimal("56.00")


@pytest.mark.parametrize(
    ("quantity", "unit_cost"),
    [
        (Decimal("0"), Decimal("1")),
        (Decimal("-1"), Decimal("1")),
        (Decimal("1"), Decimal("-1")),
    ],
)
def test_invalid_receipts_fail(quantity: Decimal, unit_cost: Decimal) -> None:
    with pytest.raises(ValueError):
        receive_cmp(Valuation(Decimal("1"), Decimal("1")), quantity, unit_cost)


def test_insufficient_stock_and_residual_value_rejected() -> None:
    with pytest.raises(ValueError):
        issue_cmp(Valuation(Decimal("2"), Decimal("20")), Decimal("3"))
    with pytest.raises(ValueError):
        receive_cmp(Valuation(Decimal("0"), Decimal("1")), Decimal("1"), Decimal("1"))


def test_fractional_cost_preserves_total_on_final_issue() -> None:
    stock = receive_cmp(Valuation(Decimal("0"), Decimal("0")), Decimal("3"), Decimal("1"))
    stock, first = issue_cmp(stock, Decimal("1"))
    stock, second = issue_cmp(stock, Decimal("2"))
    assert first + second == Decimal("3")
    assert stock.value == 0
