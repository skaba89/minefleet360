"""Calcul pur des échéances d'entretien préventif (lot 3b).

Aucune écriture en base ni création d'ordre de travail : cette couche prépare les
décisions métier avant branchement aux modèles et aux politiques RLS.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

Status = Literal["DUE", "UPCOMING", "INSUFFICIENT_DATA", "NOT_CONFIGURED"]
Trigger = Literal["KM", "HOURS", "DAYS", "INITIAL"]
BaselineSource = Literal["WORK_ORDER", "DECLARATION", "INITIAL_REQUIRED", "NONE"]


@dataclass(frozen=True)
class ServiceRule:
    km_interval: Decimal | None = None
    hours_interval: Decimal | None = None
    days_interval: int | None = None

    def __post_init__(self) -> None:
        if self.km_interval is not None and (not self.km_interval.is_finite() or self.km_interval <= 0):
            raise ValueError("km_interval doit être strictement positif et fini")
        if self.hours_interval is not None and (
            not self.hours_interval.is_finite() or self.hours_interval <= 0
        ):
            raise ValueError("hours_interval doit être strictement positif et fini")
        if self.days_interval is not None and self.days_interval <= 0:
            raise ValueError("days_interval doit être strictement positif")


@dataclass(frozen=True)
class ServiceBaseline:
    serviced_on: date | None = None
    # Valeurs cumulatives validées, jamais des compteurs bruts ayant subi un reset.
    cumulative_km: Decimal | None = None
    cumulative_hours: Decimal | None = None
    source: BaselineSource = "NONE"
    # Instant du jalon : origine des relevés de compteur à cumuler (preventive_meters_since).
    anchor_at: datetime | None = None
    # Dernier entretien déclaré inconnu et approuvé : entretien initial dû à cette date (clé = déclaration).
    initial_due_on: date | None = None
    initial_key: str | None = None


@dataclass(frozen=True)
class CurrentMeters:
    cumulative_km: Decimal | None = None
    cumulative_hours: Decimal | None = None
    # False si un reset de compteur n'a pas encore été réconcilié.
    km_reliable: bool = True
    hours_reliable: bool = True


@dataclass(frozen=True)
class DueResult:
    status: Status
    due_triggers: tuple[Trigger, ...]
    unknown_triggers: tuple[Trigger, ...]
    remaining_km: Decimal | None
    remaining_hours: Decimal | None
    due_on: date | None


def evaluate_due(
    rule: ServiceRule, baseline: ServiceBaseline, meters: CurrentMeters, as_of: date
) -> DueResult:
    """Premier seuil atteint => entretien dû ; aucune donnée manquante supposée nulle.

    Un dernier entretien déclaré inconnu (et approuvé) rend l'entretien initial dû sans attendre de seuil.
    """
    if baseline.initial_due_on is not None:
        return DueResult("DUE", ("INITIAL",), (), None, None, baseline.initial_due_on)
    due: list[Trigger] = []
    unknown: list[Trigger] = []
    remaining_km: Decimal | None = None
    remaining_hours: Decimal | None = None
    due_on: date | None = None

    if rule.km_interval is not None:
        if (
            not meters.km_reliable
            or baseline.cumulative_km is None
            or meters.cumulative_km is None
            or not baseline.cumulative_km.is_finite()
            or not meters.cumulative_km.is_finite()
            or baseline.cumulative_km < 0
            or meters.cumulative_km < baseline.cumulative_km
        ):
            unknown.append("KM")
        else:
            remaining_km = baseline.cumulative_km + rule.km_interval - meters.cumulative_km
            if remaining_km <= 0:
                due.append("KM")

    if rule.hours_interval is not None:
        if (
            not meters.hours_reliable
            or baseline.cumulative_hours is None
            or meters.cumulative_hours is None
            or not baseline.cumulative_hours.is_finite()
            or not meters.cumulative_hours.is_finite()
            or baseline.cumulative_hours < 0
            or meters.cumulative_hours < baseline.cumulative_hours
        ):
            unknown.append("HOURS")
        else:
            remaining_hours = baseline.cumulative_hours + rule.hours_interval - meters.cumulative_hours
            if remaining_hours <= 0:
                due.append("HOURS")

    if rule.days_interval is not None:
        if baseline.serviced_on is None or baseline.serviced_on > as_of:
            unknown.append("DAYS")
        else:
            due_on = baseline.serviced_on + timedelta(days=rule.days_interval)
            if as_of >= due_on:
                due.append("DAYS")

    configured = sum(x is not None for x in (rule.km_interval, rule.hours_interval, rule.days_interval))
    if not configured:
        status: Status = "NOT_CONFIGURED"
    elif due:
        status = "DUE"
    elif unknown:
        status = "INSUFFICIENT_DATA"
    else:
        status = "UPCOMING"
    return DueResult(status, tuple(due), tuple(unknown), remaining_km, remaining_hours, due_on)
