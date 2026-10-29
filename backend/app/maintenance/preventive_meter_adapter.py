"""Adapter les preuves de relevés au moteur de maintenance, sans cumul inventé."""

from app.maintenance.preventive import CurrentMeters
from app.maintenance.preventive_meter_evidence import MeterEvidence


def current_meters_from_evidence(km: MeterEvidence, hours: MeterEvidence) -> CurrentMeters:
    """Refuser le calcul par seuil tant que le cumul n'est pas réconcilié.

    Le dernier relevé brut, même positif et sans reset observé, n'est pas
    une distance cumulée certifiée depuis l'entretien de référence.
    """
    return CurrentMeters(
        cumulative_km=None,
        cumulative_hours=None,
        km_reliable=False,
        hours_reliable=False,
    )
