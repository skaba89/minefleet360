"""Tests d'autorisation GÉNÉRÉS depuis authz_matrix.yaml (D-09, MATRICE_RBAC §7.2).

L'oracle vient du YAML et de la table de décision D-05, jamais des décorateurs de routes.
- ST-01 : inventaire route ↔ permission (une route sans permission déclarée fait échouer le build).
- ST-02 : pour chaque route × (rôle, portée) non autorisé → 403 PERMISSION_DENIED, audité.
- Isolation : pour chaque route « item » autorisée, l'identifiant d'un objet d'un autre tenant
  donne un 404 indiscernable d'un UUID inexistant, sans modification.
"""

import re
import uuid
from dataclasses import dataclass

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.authz.matrix import load_matrix
from tests.conftest import API, Api, TenantFixture

MATRIX = load_matrix()
PARAM = re.compile(r"\{(\w+)\}")
SAMPLE_BODIES: dict[tuple[str, str], dict[str, object]] = {
    ("PATCH", "/sites/{site_id}"): {"name": "Nom modifié"},
    ("PATCH", "/users/{user_id}"): {"display_name": "Nom-Test modifié"},
    ("PATCH", "/tenant"): {"display_name": "Nom modifié"},
}


@dataclass(frozen=True)
class Persona:
    role: str
    scope: str
    headers: dict[str, str]

    @property
    def label(self) -> str:
        return f"{self.role}/{self.scope}"


@dataclass
class World:
    a: TenantFixture
    b: TenantFixture
    personas: list[Persona]
    b_personas: dict[str, Persona]
    a_objects: dict[str, uuid.UUID]


@pytest.fixture(scope="module")
def world(api: Api, client: TestClient) -> World:
    a, b = api.tenant(), api.tenant()
    personas = [Persona("PLATFORM_ADMIN", "PLATFORM", api.platform())]
    for code, role in MATRIX.roles.items():
        if role.tenant_kind != "CUSTOMER":
            continue
        for scope in role.allowed_scopes:
            account = api.user(a, code, scope, "S1" if scope == "SITE" else None)
            personas.append(Persona(code, scope, account.headers))
    b_personas = {
        "TENANT_ADMIN": Persona("TENANT_ADMIN", "TENANT", b.admin.headers),
        "AUDITOR": Persona("AUDITOR", "TENANT", api.user(b, "AUDITOR").headers),
    }
    hr = api.user(a, "HR")
    assignment = client.get(
        f"{API}/role-assignments", headers=a.admin.headers, params={"user_id": str(hr.user_id)}
    ).json()["items"][0]["user_role_assignment_id"]
    event = client.get(f"{API}/audit-events", headers=a.admin.headers).json()["items"][0]["audit_event_id"]
    objects = {
        "site_id": a.sites["S1"],
        "user_id": hr.user_id,
        "assignment_id": uuid.UUID(assignment),
        "event_id": uuid.UUID(event),
        "tenant_id": a.tenant_id,
    }
    return World(a, b, personas, b_personas, objects)


def _routes() -> list[tuple[str, str, str]]:
    return [
        (perm.name, route.method, route.path)
        for perm in MATRIX.permissions.values()
        if perm.tranche in ("1a",)
        for route in perm.routes
    ]


def _call(client: TestClient, method: str, path: str, headers: dict[str, str], ids: dict[str, uuid.UUID]):  # type: ignore[no-untyped-def]
    url = API + PARAM.sub(lambda m: str(ids.get(m.group(1), uuid.uuid4())), path)
    body = SAMPLE_BODIES.get((method, path))
    return client.request(method, url, headers={**headers, "If-Match": '"1"'}, json=body)


# --- ST-01 --------------------------------------------------------------------------------------------


def test_st01_every_route_declares_exactly_the_matrix_permission(client: TestClient) -> None:
    declared = MATRIX.route_permissions()
    seen: set[tuple[str, str]] = set()
    problems = []
    for route in client.app.routes:  # type: ignore[attr-defined]
        if not isinstance(route, APIRoute) or not route.path.startswith(API):
            continue
        path = route.path.removeprefix(API)
        for method in route.methods - {"HEAD", "OPTIONS"}:
            key = (method, path)
            seen.add(key)
            permission = getattr(route, "permission", "<route sans SecuredRoute>")
            if key in MATRIX.public_routes:
                if permission is not None:
                    problems.append(f"{key} est publique mais exige {permission}")
            elif declared.get(key) != permission:
                problems.append(f"{key}: code={permission} matrice={declared.get(key)}")
    missing = (set(declared) | set(MATRIX.public_routes)) - seen
    assert problems == [] and missing == set()


def test_st01_openapi_exposes_x_permission(client: TestClient) -> None:
    schema = client.get(f"{API}/openapi.json").json()
    for (method, path), permission in MATRIX.route_permissions().items():
        assert schema["paths"][API + path][method.lower()]["x-permission"] == permission


# --- ST-02 (refus) ------------------------------------------------------------------------------------


def _denied_cases() -> list[tuple[str, str, str, str, str]]:
    personas = [("PLATFORM_ADMIN", "PLATFORM")] + [
        (code, scope)
        for code, role in MATRIX.roles.items()
        if role.tenant_kind == "CUSTOMER"
        for scope in role.allowed_scopes
    ]
    return [
        (permission, method, path, role, scope)
        for permission, method, path in _routes()
        for role, scope in personas
        if scope not in MATRIX.permissions[permission].grants.get(role, ())
    ]


@pytest.mark.parametrize(("permission", "method", "path", "role", "scope"), _denied_cases())
def test_st02_role_without_permission_gets_403(
    client: TestClient, world: World, permission: str, method: str, path: str, role: str, scope: str
) -> None:
    persona = next(p for p in world.personas if p.role == role and p.scope == scope)
    resp = _call(client, method, path, persona.headers, world.a_objects)
    assert resp.status_code == 403, (persona.label, resp.text)
    assert resp.json()["code"] == "PERMISSION_DENIED"


def test_st02_denials_are_audited(client: TestClient, world: World) -> None:
    hr = next(p for p in world.personas if p.role == "HR" and p.scope == "TENANT")
    client.get(f"{API}/audit-events", headers=hr.headers)
    events = client.get(
        f"{API}/audit-events", headers=world.a.admin.headers, params={"action": "audit.event.read"}
    ).json()["items"]
    assert any(e["outcome"] == "DENIED" and e["reason"] == "PERMISSION_DENIED" for e in events)


# --- ST-02 (accès autorisés en lecture) ---------------------------------------------------------------


def _allowed_reads() -> list[tuple[str, str, str, str]]:
    cases = []
    for permission, method, path in _routes():
        if method != "GET":
            continue
        for role, scopes in MATRIX.permissions[permission].grants.items():
            cases.extend((path, permission, role, scope) for scope in scopes)
    return cases


@pytest.mark.parametrize(("path", "permission", "role", "scope"), _allowed_reads())
def test_st02_granted_reads_succeed_within_scope(
    client: TestClient, world: World, path: str, permission: str, role: str, scope: str
) -> None:
    persona = next(p for p in world.personas if p.role == role and p.scope == scope)
    resp = _call(client, "GET", path, persona.headers, world.a_objects)
    assert resp.status_code == 200, (persona.label, permission, resp.text)


def test_site_scoped_role_sees_only_its_site(client: TestClient, world: World) -> None:
    dispatcher = next(p for p in world.personas if p.role == "DISPATCHER")
    listed = client.get(f"{API}/sites", headers=dispatcher.headers).json()
    assert [s["site_id"] for s in listed["items"]] == [str(world.a.sites["S1"])] and listed["total"] == 1
    other = client.get(f"{API}/sites/{world.a.sites['S2']}", headers=dispatcher.headers)
    assert other.status_code == 404 and other.json()["code"] == "NOT_FOUND"


# --- Isolation inter-tenant ---------------------------------------------------------------------------


def _item_routes() -> list[tuple[str, str, str, str]]:
    cases = []
    for permission, method, path in _routes():
        if "{" not in path or path.startswith("/platform"):
            continue
        for role in ("TENANT_ADMIN", "AUDITOR"):
            if "TENANT" in MATRIX.permissions[permission].grants.get(role, ()):
                cases.append((permission, method, path, role))
                break
    return cases


def _strip(body: dict) -> dict:  # type: ignore[type-arg]
    return {k: v for k, v in body.items() if k != "request_id"}


@pytest.mark.parametrize(("permission", "method", "path", "role"), _item_routes())
def test_isolation_foreign_object_is_indistinguishable_from_missing(
    client: TestClient, world: World, permission: str, method: str, path: str, role: str
) -> None:
    persona = world.b_personas[role]
    before = client.get(f"{API}/audit-events", headers=world.a.admin.headers).json()["total"]
    foreign = _call(client, method, path, persona.headers, world.a_objects)
    missing = _call(client, method, path, persona.headers, {})
    assert foreign.status_code == missing.status_code == 404, (permission, foreign.text)
    assert _strip(foreign.json()) == _strip(missing.json())
    assert client.get(f"{API}/audit-events", headers=world.a.admin.headers).json()["total"] == before


def test_isolation_lists_never_include_other_tenant(client: TestClient, world: World) -> None:
    b_admin = world.b.admin.headers
    sites = client.get(f"{API}/sites", headers=b_admin).json()
    users = client.get(f"{API}/users", headers=b_admin).json()
    events = client.get(f"{API}/audit-events", headers=b_admin).json()
    assert {s["site_id"] for s in sites["items"]}.isdisjoint({str(x) for x in world.a.sites.values()})
    assert str(world.a_objects["user_id"]) not in {u["user_account_id"] for u in users["items"]}
    assert str(world.a_objects["event_id"]) not in {e["audit_event_id"] for e in events["items"]}


def test_isolation_foreign_reference_in_body_is_422(client: TestClient, world: World) -> None:
    resp = client.post(
        f"{API}/users",
        headers=world.b.admin.headers,
        json={
            "email": f"x.{uuid.uuid4().hex[:6]}@example.com",
            "display_name": "Nom-Test X",
            "role_code": "DISPATCHER",
            "scope_type": "SITE",
            "site_id": str(world.a.sites["S1"]),
        },
    )
    assert resp.status_code == 422 and resp.json()["code"] == "REFERENCE_NOT_FOUND"


def test_isolation_tenant_id_in_body_is_rejected(client: TestClient, world: World) -> None:
    resp = client.post(
        f"{API}/sites",
        headers=world.b.admin.headers,
        json={"code": "ZZ", "name": "Site intrus", "site_type": "MINE", "tenant_id": str(world.a.tenant_id)},
    )
    assert resp.status_code == 422 and resp.json()["code"] == "VALIDATION_ERROR"
