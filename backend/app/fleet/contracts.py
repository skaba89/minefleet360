"""Contrat public du module fleet (provisioning de tenant, éligibilité future des affectations)."""

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.fleet.models import Vehicle


def site_blockers(db: Session, site_id: uuid.UUID, limit: int) -> tuple[int, list[dict[str, str]]]:
    """Ressources non réformées du site courant; identifiants techniques uniquement (RLS)."""
    rows = db.execute(
        select(Vehicle.vehicle_id, func.count().over().label("total"))
        .where(Vehicle.site_id == site_id, Vehicle.status != "RETIRED")
        .order_by(Vehicle.vehicle_id)
        .limit(max(1, limit))
    ).all()
    return (int(rows[0].total) if rows else 0), [
        {"entity_type": "vehicle", "entity_id": str(row.vehicle_id)} for row in rows[: max(0, limit)]
    ]


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
