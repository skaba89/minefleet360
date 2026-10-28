"""Proposition déterministe d'échéances, sans écriture SQL ni lancement d'OT.

La clé représente un cycle d'entretien et non une exécution du planificateur.
Les doublons sont ensuite bloqués en base par la contrainte de migration 0019.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.maintenance.preventive import (
    CurrentMeters,
    ServiceBaseline,
    ServiceRule,
    Trigger,
    evaluate_due,
)


@dataclass(frozen=True)
class DueCandidate:
    trigger_kind: Trigger
    trigger_key: str
    due_on: date | None
    due_meter: Decimal | None


def due_candidates(
    rule: ServiceRule,
    baseline: ServiceBaseline,
    meters: CurrentMeters,
    as_of: date,
) -> tuple[DueCandidate, ...]:
    """Un seul événement par cycle, même si plusieurs seuils sont franchis.

    Priorité stable : calendrier, kilomètres, heures. Une échéance connue
    reste due même si un autre compteur n'est pas fiable.
    """
    result = evaluate_due(rule, baseline, meters, as_of)
    if result.status != "DUE":
        return ()

    if "DAYS" in result.due_triggers:
        assert baseline.serviced_on is not None
        assert result.due_on is not None
        return (
            DueCandidate("DAYS", "DAYS:" + baseline.serviced_on.isoformat(), result.due_on, None),
        )

    if "KM" in result.due_triggers:
        assert baseline.cumulative_km is not None
        assert rule.km_interval is not None
        threshold = baseline.cumulative_km + rule.km_interval
        key = "KM:" + str(baseline.cumulative_km.normalize())
        return (DueCandidate("KM", key, None, threshold),)

    assert "HOURS" in result.due_triggers
    assert baseline.cumulative_hours is not None
    assert rule.hours_interval is not None
    threshold = baseline.cumulative_hours + rule.hours_interval
    key = "HOURS:" + str(baseline.cumulative_hours.normalize())
    return (DueCandidate("HOURS", key, None, threshold),)
