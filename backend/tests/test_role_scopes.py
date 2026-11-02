"""Portées autorisées par rôle (décisions déléguées, docs/MATRICE_RBAC.md §6)."""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def _invite(client: TestClient, headers: dict[str, str], role: str, scope: str, site: str | None):  # type: ignore[no-untyped-def]
    body: dict[str, object] = {
        "email": f"carburant.{uuid.uuid4().hex[:8]}@example.com",
        "display_name": "Nom-Test Carburant",
        "role_code": role,
        "scope_type": scope,
    }
    if site:
        body["site_id"] = site
    return client.post(f"{API}/users", headers=headers, json=body)


def test_fuel_manager_is_a_site_role(client: TestClient, api: Api) -> None:
    t = api.tenant()
    refused = _invite(client, t.admin.headers, "FUEL_MANAGER", "TENANT", None)
    assert refused.status_code == 422 and refused.json()["code"] == "SCOPE_NOT_ALLOWED_FOR_ROLE"
    accepted = _invite(client, t.admin.headers, "FUEL_MANAGER", "SITE", str(t.sites["S1"]))
    assert accepted.status_code == 201, accepted.text


def test_roles_listing_offers_only_assignable_scopes(client: TestClient, api: Api) -> None:
    t = api.tenant()
    roles = {
        r["role_code"]: r["allowed_scopes"]
        for r in client.get(f"{API}/roles", headers=t.admin.headers).json()
    }
    assert roles["FUEL_MANAGER"] == ["SITE"]
    assert set(roles["HSE"]) == {"TENANT", "SITE"}
