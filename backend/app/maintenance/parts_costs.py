"""Agrégation prudente des coûts de pièces consommées par ordre de travail.

Aucun montant n'est inventé : un mouvement historique sans coût reste inconnu.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class WorkOrderPartsCost:
    known_total: Decimal
    valued_movements: int
    unvalued_movements: int

    @property
    def complete(self) -> bool:
        return self.unvalued_movements == 0


def aggregate_parts_cost(
    costs: list[Decimal | None], *, currency_count: int = 1
) -> WorkOrderPartsCost:
    """Agrège uniquement les coûts historiques connus, en devise homogène.

    Le résultat connu n'est pas un coût total lorsque complete est faux.
    """
    if currency_count != 1 and costs:
        raise ValueError("Les devises doivent être homogènes avant agrégation")
    if any(amount is not None and (not amount.is_finite() or amount < 0) for amount in costs):
        raise ValueError("Coût financier invalide")
    known = [amount for amount in costs if amount is not None]
    return WorkOrderPartsCost(
        known_total=sum(known, Decimal("0")),
        valued_movements=len(known),
        unvalued_movements=len(costs) - len(known),
    )
