"""Application des quotas de plan au provisionnement (lot 2b commercialisation).

Règle : un abonnement VIVANT (TRIAL/ACTIVE/SUSPENDED) borne la création des ressources
couvertes par son plan ; CANCELLED n'est plus vivant et aucune borne ne s'applique.
Un quota NULL (= illimité) et l'absence d'abonnement ne refusent jamais — la plateforme
et les sociétés de démonstration continuent de fonctionner sans abonnement.
La borne est évaluée AVANT l'écriture : usage >= limite → 422 QUOTA_EXCEEDED.

Non couvert en 2b : `document_retention_days` (appliqué par la purge GPS, chantier séparé).
"""

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.fleet.gps_binding_models import FleetGpsDeviceBinding
from app.fleet.models import Vehicle
from app.identity.models import UserAccount
from app.organization.models import Site

QUOTA_FIELDS = ("max_users", "max_sites", "max_vehicles", "max_gps_trackers")

# Emplacements stables pour les verrous consultatifs (un champ = un emplacement).
_FIELD_LOCK_SLOTS = {field: slot for slot, field in enumerate(QUOTA_FIELDS, start=1)}


def _quota_lock(tenant_id: uuid.UUID, field: str) -> tuple[int, int]:
    """Clé de verrou consultatif déterministe (société, champ) : deux sociétés concurrentes
    ne se sérialisent pas, deux champs d'une même société non plus."""
    return (int.from_bytes(tenant_id.bytes[:4], "big", signed=True), _FIELD_LOCK_SLOTS[field])


def usage_counts(db: Session, tenant_id: uuid.UUID) -> dict[str, int]:
    """Compteurs d'usage réels de la société (lot 4 : vue support plateforme, checklist d'onboarding).

    Le contexte RLS du tenant doit être posé avant l'appel (routes plateforme) — les requêtes
    filtrent déjà explicitement par tenant_id.
    """
    return {field: _usage(db, tenant_id, field) for field in QUOTA_FIELDS}


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
    """Refuse (422 QUOTA_EXCEEDED) si la borne du plan vivant est atteinte — sinon n'écrit rien.

    Le contrôle « lire puis écrire » est sérialisé par un verrou consultatif de transaction
    (société, champ) : deux provisionnements concurrents ne peuvent pas franchir la borne
    ensemble. Le verrou est libéré au commit/rollback avec l'écriture qu'il protège.
    """
    if field not in QUOTA_FIELDS:
        raise ValueError(f"Quota inconnu : {field}")
    lock_key_1, lock_key_2 = _quota_lock(auth.tenant_id, field)
    auth.db.execute(
        text("SELECT pg_advisory_xact_lock(:key_1, :key_2)"),
        {"key_1": lock_key_1, "key_2": lock_key_2},
    )
    limit = _limit_for_live_subscription(auth.db, auth.tenant_id, field)
    if limit is None:  # pas d'abonnement vivant ou quota illimité
        return
    usage = _usage(auth.db, auth.tenant_id, field)
    if usage >= limit:
        raise AppError(
            "QUOTA_EXCEEDED",
            details=[{"field": field, "limit": limit, "usage": usage}],
        )
