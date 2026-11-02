"""Garde-fous : les commandes DEMO sont techniquement impossibles hors d'une base de démonstration.

Deux verrous indépendants :
1. l'environnement applicatif (MF_ENV) ne doit pas être `production` ;
2. la base ne doit contenir AUCUN tenant client non marqué `is_demo` : une base de recette ou de production
   qui porte un seul vrai client est refusée, quelle que soit la configuration.
"""

from sqlalchemy import select

from app.core.config import Settings
from app.core.db import new_session
from app.core.tenancy import PLATFORM_TENANT_ID, set_tenant_context
from app.organization.models import Tenant


class DemoRefused(RuntimeError):
    pass


def non_demo_customer_tenants() -> list[str]:
    db = new_session()
    try:
        set_tenant_context(db, PLATFORM_TENANT_ID)
        rows = db.execute(
            select(Tenant.code)
            .where(Tenant.kind == "CUSTOMER", Tenant.is_demo.is_(False))
            .order_by(Tenant.code)
        ).scalars()
        return list(rows)
    finally:
        db.close()


def ensure_demo_database(settings: Settings) -> None:
    if settings.env == "production":
        raise DemoRefused("commande DEMO refusée : MF_ENV=production")
    foreign = non_demo_customer_tenants()
    if foreign:
        raise DemoRefused(
            f"commande DEMO refusée : la base contient {len(foreign)} tenant(s) client(s) non DEMO "
            "(utiliser une base de démonstration dédiée)"
        )
