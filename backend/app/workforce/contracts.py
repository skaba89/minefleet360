"""Contrat public du module workforce : faits d'éligibilité d'un conducteur pour les affectations.

Aucune donnée personnelle sensible (téléphone, n° de permis) n'en sort : seuls statut, site, nom affiché,
matricule (lisibles par tous les rôles qui lisent les affectations) et dates de validité.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.workforce.models import Driver, DriverLicense, DriverQualification
from app.workforce.validity import ELIGIBLE, derive_validity

__all__ = [
    "ELIGIBLE",
    "DriverFacts",
    "LicenseFact",
    "QualificationFact",
    "derive_validity",
    "driver_facts",
    "site_blockers",
]


@dataclass(frozen=True)
class LicenseFact:
    driver_license_id: uuid.UUID
    category_code: str
    status: str
    issue_date: date
    expiry_date: date


@dataclass(frozen=True)
class QualificationFact:
    """Habilitation de conduite (`DRIVING_AUTHORIZATION`) d'une catégorie d'engin (RM-023)."""

    driver_qualification_id: uuid.UUID
    vehicle_category_id: uuid.UUID
    site_id: uuid.UUID | None
    status: str
    valid_from: date
    valid_to: date | None


@dataclass(frozen=True)
class DriverFacts:
    driver_id: uuid.UUID
    site_id: uuid.UUID
    status: str
    display_name: str
    employee_number: str
    licenses: tuple[LicenseFact, ...]
    authorizations: tuple[QualificationFact, ...]


def driver_facts(
    db: Session, driver_ids: Iterable[uuid.UUID], *, lock: bool = False
) -> dict[uuid.UUID, DriverFacts]:
    """Conducteurs du tenant courant (RLS). `lock` : FOR NO KEY UPDATE (D-32)."""
    ids = sorted(set(driver_ids))
    if not ids:
        return {}
    stmt = select(Driver).where(Driver.driver_id.in_(ids)).order_by(Driver.driver_id)
    if lock:
        stmt = stmt.with_for_update(key_share=True)
    drivers = list(db.execute(stmt).scalars())
    licenses: dict[uuid.UUID, list[LicenseFact]] = {d.driver_id: [] for d in drivers}
    for lic in db.execute(select(DriverLicense).where(DriverLicense.driver_id.in_(ids))).scalars():
        licenses[lic.driver_id].append(
            LicenseFact(lic.driver_license_id, lic.category_code, lic.status, lic.issue_date, lic.expiry_date)
        )
    authorizations: dict[uuid.UUID, list[QualificationFact]] = {d.driver_id: [] for d in drivers}
    rows = db.execute(
        select(DriverQualification).where(
            DriverQualification.driver_id.in_(ids),
            DriverQualification.qualification_type == "DRIVING_AUTHORIZATION",
        )
    ).scalars()
    for q in rows:
        if q.vehicle_category_id is not None:
            authorizations[q.driver_id].append(
                QualificationFact(
                    q.driver_qualification_id,
                    q.vehicle_category_id,
                    q.site_id,
                    q.status,
                    q.valid_from,
                    q.valid_to,
                )
            )
    return {
        d.driver_id: DriverFacts(
            driver_id=d.driver_id,
            site_id=d.site_id,
            status=d.status,
            display_name=f"{d.last_name.upper()} {d.first_name}",
            employee_number=d.employee_number,
            licenses=tuple(licenses[d.driver_id]),
            authorizations=tuple(authorizations[d.driver_id]),
        )
        for d in drivers
    }


def site_blockers(db: Session, site_id: uuid.UUID, limit: int) -> tuple[int, list[dict[str, str]]]:
    """Conducteurs non inactifs du site courant; aucune identité personnelle exposée (RLS)."""
    rows = db.execute(
        select(Driver.driver_id, func.count().over().label("total"))
        .where(Driver.site_id == site_id, Driver.status != "INACTIVE")
        .order_by(Driver.driver_id)
        .limit(max(1, limit))
    ).all()
    return (int(rows[0].total) if rows else 0), [
        {"entity_type": "driver", "entity_id": str(row.driver_id)} for row in rows[: max(0, limit)]
    ]
