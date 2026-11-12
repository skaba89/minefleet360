"""Application des quotas de plan au provisionnement (lot 2b commercialisation).

Règle : un abonnement VIVANT (TRIAL/ACTIVE/SUSPENDED) borne la création des ressources
couvertes par son plan ; CANCELLED n'est plus vivant et aucune borne ne s'applique.
Un quota NULL (= illimité) et l'absence d'abonnement ne refusent jamais — la plateforme
et les sociétés de démonstration continuent de fonctionner sans abonnement.
La borne est évaluée AVANT l'écriture : usage >= limite → 422 QUOTA_EXCEEDED.

Non couvert en 2b : `document_retention_days` (appliqué par la purge GPS, chantier séparé).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.fleet.gps_binding_models import FleetGpsDeviceBinding
from app.fleet.models import Vehicle
from app.identity.models import UserAccount
from app.organization.models import Site

QUOTA_FIELDS = ("max_users", "max_sites", "max_vehicles", "max_gps_trackers")


def _usage(db: Session, tenant_id: uuid.UUID, field: str) -> int:
    if field == "max_users":
        # Utilisateurs réellement consommés : INVITED + ACTIVE (les désactivés libèrent la place).
        return db.execute(
            select(func.count())
            .select_from(UserAccount)
            .where(
                UserAccount.tenant_id == tenant_id,
                UserAccount.status != "DISABLED",
                UserAccount.anonymized_at.is_(None),
            )
        ).scalar_one()
    if field == "max_sites":
        return db.execute(
            select(func.count()).select_from(Site).where(Site.tenant_id == tenant_id)
        ).scalar_one()
    if field == "max_vehicles":
        # Les véhicules réformés ne consomment pas de quota (US-1.15 : hors parcs actifs).
        return db.execute(
            select(func.count())
            .select_from(Vehicle)
            .where(Vehicle.tenant_id == tenant_id, Vehicle.status != "RETIRED")
        ).scalar_one()
    if field == "max_gps_trackers":
        return db.execute(
            select(func.count())
            .select_from(FleetGpsDeviceBinding)
            .where(
                FleetGpsDeviceBinding.tenant_id == tenant_id,
                FleetGpsDeviceBinding.revoked_at.is_(None),
            )
        ).scalar_one()
    raise ValueError(f"Quota inconnu : {field}")


def _limit_for_live_subscription(db: Session, tenant_id: uuid.UUID, field: str) -> int | None:
    from app.billing.models import SaaSPlan, TenantSubscription

    subscription = (
        db.execute(
            select(TenantSubscription)
            .where(
                TenantSubscription.tenant_id == tenant_id,
                TenantSubscription.status.in_(("TRIAL", "ACTIVE", "SUSPENDED")),
            )
            .order_by(TenantSubscription.created_at.desc())
        )
        .scalars()
        .first()
    )
    if subscription is None:
        return None
    plan = db.get(SaaSPlan, subscription.plan_id)
    if plan is None:
        return None
    limit: int | None = getattr(plan, field)
    return limit


def ensure_quota(auth: Authorized, field: str) -> None:
    """Refuse (422 QUOTA_EXCEEDED) si la borne du plan vivant est atteinte — sinon n'écrit rien."""
    if field not in QUOTA_FIELDS:
        raise ValueError(f"Quota inconnu : {field}")
    limit = _limit_for_live_subscription(auth.db, auth.tenant_id, field)
    if limit is None:  # pas d'abonnement vivant ou quota illimité
        return
    usage = _usage(auth.db, auth.tenant_id, field)
    if usage >= limit:
        raise AppError(
            "QUOTA_EXCEEDED",
            details=[{"field": field, "limit": limit, "usage": usage}],
        )
