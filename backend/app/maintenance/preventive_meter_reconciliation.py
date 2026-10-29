"""Contrat de provenance des cumuls utilisés pour la maintenance préventive.

Aucune donnée de compteur brute n'est promue automatiquement en cumul validé.
La vérification documentaire et la réconciliation des resets restent externes.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.maintenance.preventive import CurrentMeters


@dataclass(frozen=True)
class ReconciledMeter:
    baseline_total: Decimal
    current_total: Decimal
    reconciliation_reference: str
    approved: bool
    unresolved_reset: bool = False


def _verified_total(evidence: ReconciledMeter | None) -> Decimal | None:
    if evidence is None or not evidence.approved or evidence.unresolved_reset:
        return None
    if not evidence.reconciliation_reference.strip():
        return None
    baseline = evidence.baseline_total
    current = evidence.current_total
    if not baseline.is_finite() or not current.is_finite():
        return None
    if baseline < 0 or current < baseline:
        return None
    return current


def current_meters_from_reconciliation(
    km: ReconciledMeter | None, hours: ReconciledMeter | None
) -> CurrentMeters:
    """Ne transmet au moteur que des cumuls approuvés et monotones."""
    verified_km = _verified_total(km)
    verified_hours = _verified_total(hours)
    return CurrentMeters(
        cumulative_km=verified_km,
        cumulative_hours=verified_hours,
        km_reliable=verified_km is not None,
        hours_reliable=verified_hours is not None,
    )
