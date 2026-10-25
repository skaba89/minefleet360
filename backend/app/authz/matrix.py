"""Chargement et validation de authz_matrix.yaml (D-09, MATRICE_RBAC §7.3)."""

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

MATRIX_PATH = Path(__file__).with_name("authz_matrix.yaml")
SCOPES = ("PLATFORM", "TENANT", "SITE")
TRANCHES = ("1a", "1b", "1c", "later")
_PERMISSION_NAME = re.compile(r"^[a-z]+\.[a-z_]+\.[a-z_]+$")
_ACTION_NAME = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


@dataclass(frozen=True)
class RouteSpec:
    method: str
    path: str
    shape: str
    success: int


@dataclass(frozen=True)
class RoleSpec:
    code: str
    allowed_scopes: tuple[str, ...]
    tenant_kind: str
    assignable_by_tenant: bool


@dataclass(frozen=True)
class PermissionSpec:
    name: str
    tranche: str
    kind: str
    site_bound: bool
    routes: tuple[RouteSpec, ...]
    grants: dict[str, tuple[str, ...]]
    audit_action: str | None


@dataclass(frozen=True)
class Matrix:
    tranche_courante: str
    roles: dict[str, RoleSpec]
    permissions: dict[str, PermissionSpec]
    public_routes: frozenset[tuple[str, str]]
    field_policies: dict[str, dict[str, frozenset[str]]] = field(default_factory=dict)

    def route_permissions(self) -> dict[tuple[str, str], str]:
        return {
            (route.method, route.path): perm.name
            for perm in self.permissions.values()
            for route in perm.routes
        }


class MatrixError(ValueError):
    pass


def _parse(raw: dict[str, Any]) -> Matrix:
    roles = {
        code: RoleSpec(
            code=code,
            allowed_scopes=tuple(spec["allowed_scopes"]),
            tenant_kind=spec["tenant_kind"],
            assignable_by_tenant=bool(spec["assignable_by_tenant"]),
        )
        for code, spec in raw["roles"].items()
    }
    for role in roles.values():
        if not set(role.allowed_scopes) <= set(SCOPES):
            raise MatrixError(f"portée inconnue pour {role.code}")

    permissions: dict[str, PermissionSpec] = {}
    seen_routes: set[tuple[str, str]] = set()
    for name, spec in raw["permissions"].items():
        if not _PERMISSION_NAME.match(name):
            raise MatrixError(f"nom de permission invalide : {name}")
        if spec["tranche"] not in TRANCHES:
            raise MatrixError(f"tranche invalide pour {name}")
        grants = {role: tuple(scopes) for role, scopes in (spec.get("grants") or {}).items()}
        for role, scopes in grants.items():
            if role not in roles:
                raise MatrixError(f"{name} : rôle inconnu {role}")
            if not set(scopes) <= set(roles[role].allowed_scopes):
                raise MatrixError(f"{name} : portée {scopes} non autorisée pour {role}")
        routes = tuple(RouteSpec(**route) for route in spec.get("routes") or [])
        for route in routes:
            key = (route.method, route.path)
            if key in seen_routes:
                raise MatrixError(f"route déclarée deux fois : {key}")
            seen_routes.add(key)
        audit = spec.get("audit") or {}
        action = audit.get("action")
        if action is not None and not _ACTION_NAME.match(action):
            raise MatrixError(f"{name} : action d'audit invalide {action}")
        permissions[name] = PermissionSpec(
            name=name,
            tranche=spec["tranche"],
            kind=spec["kind"],
            site_bound=bool(spec["site_bound"]),
            routes=routes,
            grants=grants,
            audit_action=action,
        )

    public = frozenset((r["method"], r["path"]) for r in raw.get("public_routes") or [])
    if public & seen_routes:
        raise MatrixError("une route publique est aussi déclarée sous une permission")

    policies = {
        entity: {fname: frozenset(rule.get("visible_to_roles", [])) for fname, rule in fields.items()}
        for entity, fields in (raw.get("field_policies") or {}).items()
    }
    for fields in policies.values():
        for visible in fields.values():
            if not visible <= set(roles):
                raise MatrixError("field_policies : rôle inconnu")
    return Matrix(raw["tranche_courante"], roles, permissions, public, policies)


@lru_cache
def load_matrix(path: Path = MATRIX_PATH) -> Matrix:
    with path.open(encoding="utf-8") as handle:
        return _parse(yaml.safe_load(handle))
