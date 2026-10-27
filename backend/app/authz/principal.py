"""Identité authentifiée et évaluation des permissions par portée (MATRICE_RBAC §1.1)."""

import uuid
from dataclasses import dataclass

from app.authz.matrix import load_matrix


@dataclass(frozen=True)
class Grant:
    role_code: str
    scope_type: str  # PLATFORM | TENANT | SITE
    site_id: uuid.UUID | None


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_kind: str
    session_id: uuid.UUID
    grants: tuple[Grant, ...]
    # Rôle soumis à la double authentification sans second facteur configuré (C-03, enrôlement doux).
    mfa_enrollment_pending: bool = False

    @property
    def role_codes(self) -> frozenset[str]:
        return frozenset(g.role_code for g in self.grants)


@dataclass(frozen=True)
class PermissionScope:
    """Résultat de l'étape 2 : la permission est portée, à l'échelle du tenant ou de certains sites."""

    permission: str
    tenant_wide: bool
    site_ids: frozenset[uuid.UUID]
    roles: frozenset[str]  # rôles qui portent effectivement la permission
    # (rôle, site) des attributions qui portent la permission ; site None = tenant entier.
    role_grants: frozenset[tuple[str, uuid.UUID | None]] = frozenset()

    def covers_site(self, site_id: uuid.UUID | None) -> bool:
        if self.tenant_wide:
            return True
        return site_id is not None and site_id in self.site_ids

    def roles_for_site(self, site_id: uuid.UUID | None) -> frozenset[str]:
        """Rôles applicables à un enregistrement : portée tenant, ou portée SITE sur CE site."""
        return frozenset(role for role, site in self.role_grants if site is None or site == site_id)


def evaluate(principal: Principal, permission: str) -> PermissionScope | None:
    """None = aucune attribution active ne porte la permission (→ 403, évalué avant toute recherche)."""
    spec = load_matrix().permissions.get(permission)
    if spec is None:
        return None
    tenant_wide = False
    sites: set[uuid.UUID] = set()
    roles: set[str] = set()
    role_grants: set[tuple[str, uuid.UUID | None]] = set()
    for grant in principal.grants:
        allowed_scopes = spec.grants.get(grant.role_code, ())
        if grant.scope_type not in allowed_scopes:
            continue
        roles.add(grant.role_code)
        if grant.scope_type in ("TENANT", "PLATFORM"):
            tenant_wide = True
            role_grants.add((grant.role_code, None))
        elif grant.site_id is not None:
            sites.add(grant.site_id)
            role_grants.add((grant.role_code, grant.site_id))
    if not roles:
        return None
    return PermissionScope(
        permission, tenant_wide, frozenset(sites), frozenset(roles), frozenset(role_grants)
    )


def masked_fields(entity: str, scope: PermissionScope, site_id: uuid.UUID | None = None) -> frozenset[str]:
    """Champs restreints à retirer pour CET enregistrement (D-15).

    Un champ n'est visible que si un rôle autorisé est détenu en portée TENANT ou sur le site de
    l'enregistrement : un rôle HR sur S1 ne révèle pas le téléphone d'un conducteur de S2 (revue 1b).
    Pour une entité sans site (`site_id` None), seules les attributions de portée TENANT comptent.
    """
    policy = load_matrix().field_policies.get(entity, {})
    applicable = scope.roles_for_site(site_id) if site_id is not None else scope.roles_for_site(None)
    return frozenset(name for name, allowed in policy.items() if not allowed & applicable)


def restricted_fields(entity: str) -> frozenset[str]:
    """Champs soumis à une politique de visibilité : jamais de valeur dans l'audit."""
    return frozenset(load_matrix().field_policies.get(entity, {}))


def mask(
    entity: str, scope: PermissionScope, data: dict[str, object], site_id: uuid.UUID | None = None
) -> dict[str, object]:
    """Retire de la réponse les champs restreints non visibles pour cet enregistrement (masquage total)."""
    hidden = masked_fields(entity, scope, site_id)
    return {key: value for key, value in data.items() if key not in hidden}
