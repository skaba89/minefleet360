"""Politique de valorisation des réceptions sans inventer les coûts historiques."""

from decimal import Decimal

from app.maintenance.valuation import Valuation, receive_cmp


def prepare_valued_receipt(
    *,
    on_hand: Decimal,
    stock_value: Decimal | None,
    existing_currency: str | None,
    quantity: Decimal,
    unit_cost: Decimal,
    currency: str,
) -> Valuation:
    """Valide une réception chiffrée avant toute écriture transactionnelle.

    Un solde historique positif sans valeur connue est bloqué afin de ne pas
    produire un CMP mensonger. La transaction PostgreSQL devra revalider ces
    conditions sous verrou de ligne avant de modifier le solde et le journal.
    """
    if len(currency) != 3 or not currency.isascii() or not currency.isalpha() or not currency.isupper():
        raise ValueError("Devise ISO 4217 attendue (trois lettres majuscules)")
    if not all(x.is_finite() for x in (on_hand, quantity, unit_cost)):
        raise ValueError("Montant ou quantité non fini")
    if stock_value is not None and not stock_value.is_finite():
        raise ValueError("Valeur de stock non finie")
    if on_hand < 0 or quantity <= 0 or unit_cost < 0:
        raise ValueError("Quantité ou prix invalide")
    if stock_value is None:
        if existing_currency is not None or on_hand != 0:
            raise ValueError("Stock historique non valorisé : inventaire d'ouverture requis")
        previous = Valuation(Decimal("0"), Decimal("0"))
    else:
        if existing_currency != currency:
            raise ValueError("Conversion de devise nécessaire")
        previous = Valuation(on_hand, stock_value)
    return receive_cmp(previous, quantity, unit_cost)
