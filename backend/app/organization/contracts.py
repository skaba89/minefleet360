"""Contrat public du module organization (sites et fuseaux pour les autres modules)."""

import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz.principal import PermissionScope
from app.organization.models import Site, Tenant


def site_in_scope(db: Session, scope: PermissionScope, site_id: uuid.UUID) -> Site | None:
    """Site du tenant courant (RLS) ET couvert par la portée ; sinon None (→ 422 REFERENCE_NOT_FOUND)."""
    site = db.get(Site, site_id)
    if site is None or not scope.covers_site(site.site_id):
        return None
    return site


def site_timezone(db: Session, site_id: uuid.UUID) -> ZoneInfo:
    """Fuseau d'affichage et de calcul des échéances : celui du site, sinon celui du tenant (H4)."""
    row = db.execute(
        select(Site.timezone, Tenant.default_timezone)
        .join(Tenant, Tenant.tenant_id == Site.tenant_id)
        .where(Site.site_id == site_id)
    ).one()
    return ZoneInfo(row.timezone or row.default_timezone)


def local_date(db: Session, site_id: uuid.UUID, instant: datetime) -> date:
    return instant.astimezone(site_timezone(db, site_id)).date()
