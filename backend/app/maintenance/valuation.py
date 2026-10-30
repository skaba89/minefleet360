"""Calculs purs pour le coût moyen pondéré mobile des pièces.

Ne modifie aucun stock : la persistance et les transactions seront intégrées
dans un lot distinct après validation de la méthode comptable.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class Valuation:
    quantity: Decimal
    value: Decimal


def receive_cmp(stock: Valuation, quantity: Decimal, unit_cost: Decimal) -> Valuation:
    """Ajoute une réception au coût historique sans arrondir prématurément."""
    if stock.quantity < 0 or stock.value < 0 or quantity <= 0 or unit_cost < 0:
        raise ValueError("Quantité ou coût invalide")
    if stock.quantity == 0 and stock.value != 0:
        raise ValueError("Stock nul avec valeur résiduelle")
    return Valuation(stock.quantity + quantity, stock.value + quantity * unit_cost)


def issue_cmp(stock: Valuation, quantity: Decimal) -> tuple[Valuation, Decimal]:
    """Valorise une sortie au CMP avant sortie; retourne (nouveau stock, coût)."""
    if stock.quantity <= 0 or stock.value < 0 or quantity <= 0 or quantity > stock.quantity:
        raise ValueError("Sortie impossible ou coût invalide")
    unit_cost = stock.value / stock.quantity
    if quantity == stock.quantity:
        return Valuation(Decimal("0"), Decimal("0")), stock.value
    issue_value = (quantity * unit_cost).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    return Valuation(stock.quantity - quantity, stock.value - issue_value), issue_value
