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

    @property
    def role_codes(self) -> frozenset[str]:
        return frozenset(g.role_code for g in self.grants)


@dataclass(frozen=True)
class PermissionScope:
    """Résultat de l'étape 2 : la permission est portée, à l'échelle du tenant ou de certains sites."""

    permission: str
    tenant_wide: bool
    site_ids: frozenset[uuid.UUID]
    roles: frozenset[str]  # rôles qui portent effectivement la permission (masquage de champs)

    def covers_site(self, site_id: uuid.UUID | None) -> bool:
        if self.tenant_wide:
            return True
        return site_id is not None and site_id in self.site_ids


def evaluate(principal: Principal, permission: str) -> PermissionScope | None:
    """None = aucune attribution active ne porte la permission (→ 403, évalué avant toute recherche)."""
    spec = load_matrix().permissions.get(permission)
    if spec is None:
        return None
    tenant_wide = False
    sites: set[uuid.UUID] = set()
    roles: set[str] = set()
    for grant in principal.grants:
        allowed_scopes = spec.grants.get(grant.role_code, ())
        if grant.scope_type not in allowed_scopes:
            continue
        roles.add(grant.role_code)
        if grant.scope_type in ("TENANT", "PLATFORM"):
            tenant_wide = True
        elif grant.site_id is not None:
            sites.add(grant.site_id)
    if not roles:
        return None
    return PermissionScope(permission, tenant_wide, frozenset(sites), frozenset(roles))


def visible_fields(entity: str, scope: PermissionScope) -> frozenset[str] | None:
    """Champs restreints visibles pour ces rôles ; None si l'entité n'a pas de politique."""
    policy = load_matrix().field_policies.get(entity)
    if policy is None:
        return None
    return frozenset(name for name, allowed in policy.items() if allowed & scope.roles)


def masked_fields(entity: str, scope: PermissionScope) -> frozenset[str]:
    policy = load_matrix().field_policies.get(entity, {})
    return frozenset(name for name, allowed in policy.items() if not allowed & scope.roles)
