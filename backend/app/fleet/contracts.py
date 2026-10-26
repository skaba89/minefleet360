"""Contrat public du module fleet (provisioning de tenant, éligibilité future des affectations)."""

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session


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
