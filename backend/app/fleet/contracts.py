"""Contrat public du module fleet (provisioning de tenant, faits d'éligibilité des affectations)."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.fleet.models import Vehicle, VehicleCategory, VehicleCategoryLicense


@dataclass(frozen=True)
class VehicleFacts:
    """Ce dont l'affectation a besoin d'un véhicule (RM-030 a, c, d), sans exposer le modèle ORM."""

    vehicle_id: uuid.UUID
    site_id: uuid.UUID
    status: str
    fleet_number: str
    vehicle_category_id: uuid.UUID
    requires_driver: bool
    requires_internal_authorization: bool
    # Vide = aucun permis d'État exigé par le catalogue (RM-022, valeurs fictives à valider : C-07).
    required_license_categories: frozenset[str]


def vehicle_facts(
    db: Session, vehicle_ids: Iterable[uuid.UUID], *, lock: bool = False
) -> dict[uuid.UUID, VehicleFacts]:
    """Véhicules du tenant courant (RLS). `lock` : FOR NO KEY UPDATE (D-32) contre un changement de statut."""
    ids = sorted(set(vehicle_ids))
    if not ids:
        return {}
    stmt = (
        select(Vehicle, VehicleCategory)
        .join(VehicleCategory, VehicleCategory.vehicle_category_id == Vehicle.vehicle_category_id)
        .where(Vehicle.vehicle_id.in_(ids))
        .order_by(Vehicle.vehicle_id)
    )
    if lock:
        stmt = stmt.with_for_update(key_share=True, of=Vehicle)
    rows = db.execute(stmt).all()
    category_ids = {category.vehicle_category_id for _, category in rows}
    licenses: dict[uuid.UUID, set[str]] = {c: set() for c in category_ids}
    for category_id, code in db.execute(
        select(
            VehicleCategoryLicense.vehicle_category_id, VehicleCategoryLicense.license_category_code
        ).where(VehicleCategoryLicense.vehicle_category_id.in_(category_ids))
    ):
        licenses[category_id].add(code)
    return {
        vehicle.vehicle_id: VehicleFacts(
            vehicle_id=vehicle.vehicle_id,
            site_id=vehicle.site_id,
            status=vehicle.status,
            fleet_number=vehicle.fleet_number,
            vehicle_category_id=category.vehicle_category_id,
            requires_driver=category.requires_driver,
            requires_internal_authorization=category.requires_internal_authorization,
            required_license_categories=frozenset(licenses[category.vehicle_category_id]),
        )
        for vehicle, category in rows
    }


def seed_tenant_catalog(db: Session, tenant_id: uuid.UUID) -> int:
    """Copie le catalogue de référence global dans le tenant (D-18). Contexte courant = tenant_id."""
    created = db.execute(
        text(
            """
            INSERT INTO vehicle_category (tenant_id, code, label_fr, family, requires_driver,
                requires_internal_authorization, has_odometer, has_hour_meter, is_system)
            SELECT :tid, code, label_fr, family, requires_driver, requires_internal_authorization,
                   has_odometer, has_hour_meter, true
            FROM vehicle_category_template
            """
        ),
        {"tid": str(tenant_id)},
    )
    db.execute(
        text(
            """
            INSERT INTO vehicle_category_license_category
                (tenant_id, vehicle_category_id, license_category_code)
            SELECT vc.tenant_id, vc.vehicle_category_id, l.license_category_code
            FROM vehicle_category vc
            JOIN vehicle_category_template_license l ON l.category_code = vc.code
            WHERE vc.tenant_id = :tid
            """
        ),
        {"tid": str(tenant_id)},
    )
    return int(getattr(created, "rowcount", 0) or 0)
