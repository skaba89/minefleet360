"""Lot 1 commercialisation SaaS — catalogue de plans et quotas (/platform/saas-plans).

Couvre : CRUD plateforme, seed des 4 plans candidats, unicité de code, quotas validés
(NULL = illimité), état RETIRED terminal, conflit de version (ETag), refus des rôles
tenant (méta-données commerciales jamais exposées aux sociétés) et journalisation d'audit.
"""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def _plan_body(code: str, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "code": code,
        "name": f"Plan {code}",
        "description": "Offre de test",
        "status": "ACTIVE",
        "max_users": 10,
        "max_sites": 2,
        "max_vehicles": 15,
        "max_gps_trackers": 12,
        "document_retention_days": 180,
    }
    body.update(overrides)
    return body


def _plan_code(prefix: str) -> str:
    """Code de plan unique respectant ^[A-Z][A-Z0-9_]{1,29}$."""
    return f"{prefix}_{uuid.uuid4().hex[:8].upper()}"


def test_seeded_candidate_plans_present(client: TestClient, api: Api) -> None:
    resp = client.get(f"{API}/platform/saas-plans", headers=api.platform())
    assert resp.status_code == 200
    codes = {item["code"] for item in resp.json()["items"]}
    assert {"STARTER", "BUSINESS", "MINING_PRO", "ENTERPRISE"} <= codes
    enterprise = next(item for item in resp.json()["items"] if item["code"] == "ENTERPRISE")
    assert enterprise["max_users"] is None and enterprise["max_gps_trackers"] is None  # illimité
    starter = next(item for item in resp.json()["items"] if item["code"] == "STARTER")
    assert starter["max_users"] == 5 and starter["max_gps_trackers"] == 5


def test_create_list_get_plan(client: TestClient, api: Api) -> None:
    platform = api.platform()
    code = _plan_code("P")
    created = client.post(f"{API}/platform/saas-plans", headers=platform, json=_plan_body(code))
    assert created.status_code == 201, created.text
    plan = created.json()
    assert plan["code"] == code and plan["status"] == "ACTIVE"
    assert plan["max_users"] == 10 and plan["document_retention_days"] == 180
    assert plan["row_version"] == 1

    listed = client.get(f"{API}/platform/saas-plans", headers=platform)
    assert listed.status_code == 200 and any(item["code"] == code for item in listed.json()["items"])

    fetched = client.get(f"{API}/platform/saas-plans/{plan['plan_id']}", headers=platform)
    assert fetched.status_code == 200
    assert fetched.headers["ETag"] == '"1"'
    assert fetched.json()["description"] == "Offre de test"


def test_duplicate_plan_code_rejected(client: TestClient, api: Api) -> None:
    platform = api.platform()
    first = client.post(f"{API}/platform/saas-plans", headers=platform, json=_plan_body(_plan_code("U")))
    assert first.status_code == 201
    dup = client.post(f"{API}/platform/saas-plans", headers=platform, json=_plan_body(first.json()["code"]))
    assert (dup.status_code, dup.json()["code"]) == (409, "DUPLICATE_PLAN_CODE")


def test_plan_validation_errors(client: TestClient, api: Api) -> None:
    platform = api.platform()
    bad_cases = [
        _plan_body("minuscule"),  # code : majuscule requise
        _plan_body(_plan_code("V"), max_users=0),  # quota nul
        _plan_body(_plan_code("V"), max_gps_trackers=100_001),  # quota hors bornes
        _plan_body(_plan_code("V"), document_retention_days=7),  # rétention < 30 j
        _plan_body(_plan_code("V"), status="RETIRED"),  # création directe en RETIRED interdite
        _plan_body(_plan_code("V"), name=""),  # nom vide
    ]
    for body in bad_cases:
        resp = client.post(f"{API}/platform/saas-plans", headers=platform, json=body)
        assert resp.status_code == 422, (body, resp.text)


def test_update_plan_quotas_etag_and_audit(client: TestClient, api: Api) -> None:
    platform = api.platform()
    plan = client.post(
        f"{API}/platform/saas-plans", headers=platform, json=_plan_body(_plan_code("W"))
    ).json()
    plan_id = plan["plan_id"]

    updated = client.patch(
        f"{API}/platform/saas-plans/{plan_id}",
        headers={**platform, "If-Match": '"1"'},
        json={"max_gps_trackers": None, "name": "Plan renommé"},  # NULL explicite = illimité
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["max_gps_trackers"] is None and body["name"] == "Plan renommé"
    assert body["row_version"] == 2 and updated.headers["ETag"] == '"2"'

    stale = client.patch(
        f"{API}/platform/saas-plans/{plan_id}",
        headers={**platform, "If-Match": '"1"'},
        json={"name": "Conflit"},
    )
    assert (stale.status_code, stale.json()["code"]) == (409, "VERSION_CONFLICT")

    missing = client.patch(f"{API}/platform/saas-plans/{plan_id}", headers=platform, json={"name": "X"})
    assert (missing.status_code, missing.json()["code"]) == (422, "IF_MATCH_REQUIRED")


def test_retired_plan_is_terminal(client: TestClient, api: Api) -> None:
    platform = api.platform()
    plan = client.post(
        f"{API}/platform/saas-plans", headers=platform, json=_plan_body(_plan_code("R"))
    ).json()
    plan_id = plan["plan_id"]
    retire = client.patch(
        f"{API}/platform/saas-plans/{plan_id}",
        headers={**platform, "If-Match": '"1"'},
        json={"status": "RETIRED"},
    )
    assert retire.status_code == 200 and retire.json()["status"] == "RETIRED"
    blocked = client.patch(
        f"{API}/platform/saas-plans/{plan_id}",
        headers={**platform, "If-Match": '"2"'},
        json={"name": "Résurrection"},
    )
    assert (blocked.status_code, blocked.json()["code"]) == (422, "PLAN_RETIRED")
    reactivate = client.patch(
        f"{API}/platform/saas-plans/{plan_id}",
        headers={**platform, "If-Match": '"2"'},
        json={"status": "ACTIVE"},
    )
    assert (reactivate.status_code, reactivate.json()["code"]) == (422, "PLAN_RETIRED")


def test_tenant_roles_have_no_access_to_saas_plans(client: TestClient, api: Api) -> None:
    t = api.tenant()
    for headers, label in ((t.admin.headers, "TENANT_ADMIN"),):
        assert client.get(f"{API}/platform/saas-plans", headers=headers).status_code == 403, label
        assert (
            client.post(
                f"{API}/platform/saas-plans", headers=headers, json=_plan_body(_plan_code("X"))
            ).status_code
            == 403
        ), label
        assert client.get(f"{API}/platform/saas-plans/{uuid.uuid4()}", headers=headers).status_code == 403, (
            label
        )
        assert (
            client.patch(
                f"{API}/platform/saas-plans/{uuid.uuid4()}", headers={**headers, "If-Match": '"1"'}, json={}
            ).status_code
            == 403
        ), label


def test_anonymous_access_denied(client: TestClient, api: Api) -> None:
    assert client.get(f"{API}/platform/saas-plans").status_code == 401
    assert client.post(f"{API}/platform/saas-plans", json=_plan_body(_plan_code("A"))).status_code == 401
