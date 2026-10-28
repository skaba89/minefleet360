"""Éligibilité d'un couple conducteur ↔ véhicule (RM-030, RM-031) et conformité dérivée (RM-036, D-12).

Fonction pure : aucune lecture en base, horloge et fuseau fournis par l'appelant.
Une échéance au jour J est valable jusqu'au début du jour J+1 au fuseau du site (RM-021).
"""

import datetime as dt
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.fleet.contracts import UNDATED_DOCUMENT_TYPES, DocumentFact, VehicleFacts
from app.workforce.contracts import ELIGIBLE, DriverFacts, derive_validity


@dataclass(frozen=True)
class Finding:
    code: str
    date: dt.date | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {"code": self.code, "date": self.date.isoformat() if self.date else None}


@dataclass
class Evaluation:
    reasons: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    license_ids: list[str] = field(default_factory=list)
    qualification_ids: list[str] = field(default_factory=list)

    @property
    def eligible(self) -> bool:
        return not self.reasons


def end_instant(day: date, tz: ZoneInfo) -> datetime:
    """Premier instant où une pièce échue le jour `day` n'est plus valable (début de J+1, heure du site)."""
    return datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)


def _covers(expiry: date | None, end: datetime | None, tz: ZoneInfo) -> bool:
    return expiry is None or end is None or end <= end_instant(expiry, tz)


def _check_licenses(
    ev: Evaluation,
    vehicle: VehicleFacts,
    driver: DriverFacts,
    start: datetime,
    end: datetime | None,
    tz: ZoneInfo,
    warning_days: int,
) -> date | None:
    """Échéance retenue (la plus lointaine des permis éligibles), ou None si aucun permis n'est exigé."""
    required = vehicle.required_license_categories
    if not required:
        return None
    candidates = [lic for lic in driver.licenses if lic.category_code in required]
    if not driver.licenses:
        ev.reasons.append(Finding("DRIVER_LICENSE_MISSING"))
        return None
    if not candidates:
        ev.reasons.append(Finding("DRIVER_LICENSE_CATEGORY_MISSING"))
        return None
    validity = {
        lic.driver_license_id: derive_validity(
            stored_status=lic.status,
            valid_from=lic.issue_date,
            valid_until=lic.expiry_date,
            now=start,
            tz=tz,
            warning_days=warning_days,
        )
        for lic in candidates
    }
    valid = [lic for lic in candidates if validity[lic.driver_license_id] in ELIGIBLE]
    if not valid:
        ev.reasons.append(Finding("DRIVER_LICENSE_EXPIRED", max(lic.expiry_date for lic in candidates)))
        return None
    covering = [lic for lic in valid if _covers(lic.expiry_date, end, tz)]
    if not covering:
        ev.reasons.append(Finding("DRIVER_LICENSE_EXPIRES_BEFORE_END", max(lic.expiry_date for lic in valid)))
        return None
    best = max(covering, key=lambda lic: lic.expiry_date)
    ev.license_ids.append(str(best.driver_license_id))
    if validity[best.driver_license_id] == "EXPIRING":
        ev.warnings.append(Finding("LICENSE_EXPIRING", best.expiry_date))
    return best.expiry_date


def _check_authorization(
    ev: Evaluation,
    vehicle: VehicleFacts,
    driver: DriverFacts,
    start: datetime,
    end: datetime | None,
    tz: ZoneInfo,
    warning_days: int,
) -> date | None:
    """Habilitation de conduite de la catégorie (RM-023) ; renvoie son échéance (None = sans échéance)."""
    if not vehicle.requires_internal_authorization:
        return None
    candidates = [
        q
        for q in driver.authorizations
        if q.vehicle_category_id == vehicle.vehicle_category_id and q.site_id in (None, vehicle.site_id)
    ]
    if not candidates:
        ev.reasons.append(Finding("DRIVER_QUALIFICATION_MISSING"))
        return None
    validity = {
        q.driver_qualification_id: derive_validity(
            stored_status=q.status,
            valid_from=q.valid_from,
            valid_until=q.valid_to,
            now=start,
            tz=tz,
            warning_days=warning_days,
        )
        for q in candidates
    }
    valid = [q for q in candidates if validity[q.driver_qualification_id] in ELIGIBLE]
    if not valid:
        ends = [q.valid_to for q in candidates if q.valid_to is not None]
        ev.reasons.append(Finding("DRIVER_QUALIFICATION_EXPIRED", max(ends) if ends else None))
        return None
    covering = [q for q in valid if _covers(q.valid_to, end, tz)]
    if not covering:
        ends = [q.valid_to for q in valid if q.valid_to is not None]
        ev.reasons.append(Finding("DRIVER_QUALIFICATION_EXPIRES_BEFORE_END", max(ends) if ends else None))
        return None
    best = max(covering, key=lambda q: q.valid_to or date.max)
    ev.qualification_ids.append(str(best.driver_qualification_id))
    if validity[best.driver_qualification_id] == "EXPIRING":
        ev.warnings.append(Finding("QUALIFICATION_EXPIRING", best.valid_to))
    return best.valid_to


def _check_documents(
    ev: Evaluation,
    vehicle: VehicleFacts,
    start: datetime,
    end: datetime | None,
    tz: ZoneInfo,
) -> date | None:
    """RM-104 / D-42 : un exemplaire valide de chaque document exigé par la catégorie du véhicule.

    Manquant (jamais saisi) : avertissement ou blocage selon la politique ; échu, retiré ou pas encore
    valide : toujours bloquant. Renvoie l'échéance la plus proche des exemplaires retenus.
    """
    by_type: dict[str, list[DocumentFact]] = {t: [] for t in vehicle.required_documents}
    for doc in vehicle.documents:
        by_type.setdefault(doc.doc_type, []).append(doc)
    ends: list[date] = []
    for docs in by_type.values():
        if not docs:
            finding = Finding("VEHICLE_DOCUMENT_MISSING")
            (ev.reasons if vehicle.missing_documents_block else ev.warnings).append(finding)
            continue
        validity = {
            d.vehicle_document_id: derive_validity(
                stored_status=d.status,
                valid_from=d.valid_from,
                valid_until=d.valid_until,
                now=start,
                tz=tz,
                warning_days=vehicle.document_warning_days,
            )
            for d in docs
        }
        # Défense en profondeur : un document non daté (hors carte grise) n'est jamais retenu.
        valid = [
            d
            for d in docs
            if validity[d.vehicle_document_id] in ELIGIBLE
            and (d.valid_until is not None or d.doc_type in UNDATED_DOCUMENT_TYPES)
        ]
        if not valid:
            future = all(validity[d.vehicle_document_id] == "NOT_YET_VALID" for d in docs)
            dated = [d.valid_until for d in docs if d.valid_until is not None]
            code = "VEHICLE_DOCUMENT_NOT_YET_VALID" if future else "VEHICLE_DOCUMENT_EXPIRED"
            ev.reasons.append(Finding(code, max(dated) if dated else None))
            continue
        covering = [d for d in valid if _covers(d.valid_until, end, tz)]
        if not covering:
            dated = [d.valid_until for d in valid if d.valid_until is not None]
            ev.reasons.append(Finding("VEHICLE_DOCUMENT_EXPIRES_BEFORE_END", max(dated) if dated else None))
            continue
        best = max(covering, key=lambda d: d.valid_until or date.max)
        if validity[best.vehicle_document_id] == "EXPIRING":
            ev.warnings.append(Finding("VEHICLE_DOCUMENT_EXPIRING", best.valid_until))
        if best.valid_until is not None:
            ends.append(best.valid_until)
    return min(ends) if ends else None


def evaluate(
    vehicle: VehicleFacts,
    driver: DriverFacts,
    *,
    start: datetime,
    end: datetime | None,
    tz: ZoneInfo,
    warning_days: int,
) -> Evaluation:
    """Tous les motifs d'inéligibilité à `start` et, si `end` est fourni, sur tout l'intervalle (D-29)."""
    ev = Evaluation()
    if driver.status != "ACTIVE":
        ev.reasons.append(Finding("DRIVER_NOT_ACTIVE"))
    if vehicle.status != "AVAILABLE":
        ev.reasons.append(Finding("VEHICLE_NOT_AVAILABLE"))
    if not vehicle.requires_driver:
        ev.reasons.append(Finding("VEHICLE_CATEGORY_WITHOUT_DRIVER"))
    license_end = _check_licenses(ev, vehicle, driver, start, end, tz, warning_days)
    authorization_end = _check_authorization(ev, vehicle, driver, start, end, tz, warning_days)
    document_end = _check_documents(ev, vehicle, start, end, tz)
    if end is None and ev.eligible:
        # Intervalle ouvert : valable au début seulement ; la prochaine échéance est signalée (US-1.22 R5).
        ends = [d for d in (license_end, authorization_end, document_end) if d is not None]
        if ends:
            ev.warnings.append(Finding("NEXT_EXPIRY", min(ends)))
    return ev


# Conformité d'une affectation ACTIVE (US-1.25) : motifs dérivés de l'évaluation à l'instant courant.
_COMPLIANCE_CODES = {
    "DRIVER_NOT_ACTIVE": "DRIVER_NOT_ACTIVE",
    "VEHICLE_NOT_AVAILABLE": "VEHICLE_NOT_AVAILABLE",
    "DRIVER_LICENSE_MISSING": "LICENSE_EXPIRED",
    "DRIVER_LICENSE_CATEGORY_MISSING": "LICENSE_EXPIRED",
    "DRIVER_LICENSE_EXPIRED": "LICENSE_EXPIRED",
    "DRIVER_QUALIFICATION_MISSING": "QUALIFICATION_EXPIRED",
    "DRIVER_QUALIFICATION_EXPIRED": "QUALIFICATION_EXPIRED",
    "VEHICLE_DOCUMENT_EXPIRED": "VEHICLE_DOCUMENT_EXPIRED",
    "VEHICLE_DOCUMENT_NOT_YET_VALID": "VEHICLE_DOCUMENT_EXPIRED",
    "VEHICLE_DOCUMENT_MISSING": "VEHICLE_DOCUMENT_MISSING",
}


def compliance(
    vehicle: VehicleFacts, driver: DriverFacts, *, now: datetime, tz: ZoneInfo, warning_days: int
) -> tuple[list[Finding], list[Finding]]:
    """(motifs de non-conformité, avertissements) ; aucun statut stocké n'est modifié (D-12)."""
    ev = evaluate(vehicle, driver, start=now, end=None, tz=tz, warning_days=warning_days)
    reasons = [Finding(_COMPLIANCE_CODES[r.code], r.date) for r in ev.reasons if r.code in _COMPLIANCE_CODES]
    warnings = [w for w in ev.warnings if w.code != "NEXT_EXPIRY"]
    return reasons, warnings
