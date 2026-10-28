"""Validité DÉRIVÉE des permis, habilitations et documents de véhicule (D-03 : jamais stockée).

Règle (US-1.18 A8) : une échéance au jour J est valable jusqu'au début du jour J+1 **au fuseau du site**
(exclu). Le statut administratif stocké (SUSPENDED, WITHDRAWN, REVOKED) prime sur les dates.
"""

from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

Validity = Literal["VALID", "EXPIRING", "EXPIRED", "NOT_YET_VALID", "SUSPENDED", "WITHDRAWN", "REVOKED"]
ELIGIBLE: frozenset[str] = frozenset({"VALID", "EXPIRING"})  # EXPIRING : éligible avec avertissement


def derive_validity(
    *,
    stored_status: str,
    valid_from: date | None,
    valid_until: date | None,
    now: datetime,
    tz: ZoneInfo,
    warning_days: int,
) -> Validity:
    if stored_status != "VALID":
        return stored_status  # type: ignore[return-value]
    today = now.astimezone(tz).date()
    if valid_from is not None and today < valid_from:
        return "NOT_YET_VALID"
    if valid_until is None:
        return "VALID"
    if today > valid_until:
        return "EXPIRED"
    if valid_until <= today + timedelta(days=warning_days):
        return "EXPIRING"
    return "VALID"
