"""Tenant and role guards for replenishment drafts."""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def test_replenishment_drafts_require_role_and_site_scope(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    storekeeper = api.user(tenant, "STOREKEEPER", "SITE", "MINE")
    driver = api.user(tenant, "DRIVER", "SITE", "MINE")
    other = api.tenant(sites=("OTHER",))
    for headers in (storekeeper.headers, driver.headers):
        response = client.get(f"{API}/part-replenishments", headers=headers)
        assert response.status_code == (200 if headers == storekeeper.headers else 403)
    out_of_scope = client.get(
        f"{API}/part-replenishments",
        headers=storekeeper.headers,
        params={"site_id": str(other.sites["OTHER"])},
    )
    assert out_of_scope.status_code == 404
    forbidden_create = client.post(
        f"{API}/part-replenishments",
        headers=driver.headers,
        json={
            "spare_part_store_id": str(other.sites["OTHER"]),
            "spare_part_id": str(other.sites["OTHER"]),
            "quantity": "2",
            "reference": "REF-TEST",
        },
    )
    assert forbidden_create.status_code == 403


def test_replenishment_submit_requires_permission(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    driver = api.user(tenant, "DRIVER", "SITE", "MINE")
    response = client.post(
        f"{API}/part-replenishments/00000000-0000-4000-8000-000000000011/submit",
        headers=driver.headers,
    )
    assert response.status_code == 403


def test_replenishment_decision_requires_permission(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    driver = api.user(tenant, "DRIVER", "SITE", "MINE")
    response = client.post(
        f"{API}/part-replenishments/00000000-0000-4000-8000-000000000011/decision",
        headers=driver.headers,
        json={"action": "APPROVE", "note": "Contrôle effectué"},
    )
    assert response.status_code == 403


def test_replenishment_filter_rejects_invalid_status(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    storekeeper = api.user(tenant, "STOREKEEPER", "SITE", "MINE")
    response = client.get(
        f"{API}/part-replenishments",
        headers=storekeeper.headers,
        params={"request_status": "UNRECOGNIZED"},
    )
    assert response.status_code == 422


def test_replenishment_filter_accepts_all_valid_statuses(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    storekeeper = api.user(tenant, "STOREKEEPER", "SITE", "MINE")
    for request_status in ("DRAFT", "SUBMITTED", "APPROVED", "REJECTED"):
        response = client.get(
            f"{API}/part-replenishments",
            headers=storekeeper.headers,
            params={"request_status": request_status},
        )
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 0


def test_replenishment_submit_then_decision_happy_path(client: TestClient, api: Api) -> None:
    """Régression : mf_app doit pouvoir UPDATE spare_part_replenishment (0042 n'accordait que
    SELECT, INSERT — tout submit/décision répondait 500 par 42501)."""
    tenant = api.tenant(sites=("MINE",))
    storekeeper = api.user(tenant, "STOREKEEPER", "SITE", "MINE")
    manager = api.user(tenant, "OPS_MANAGER", "TENANT")
    suffix = uuid.uuid4().hex[:8].upper()
    part = client.post(
        f"{API}/parts",
        headers=storekeeper.headers,
        json={"code": f"REGR-{suffix}", "name": f"Pièce régression {suffix}", "unit": "EACH"},
    )
    assert part.status_code == 201, part.text
    store = client.post(
        f"{API}/part-stores",
        headers=storekeeper.headers,
        json={"site_id": str(tenant.sites["MINE"]), "code": f"MAG-{suffix}", "name": f"Magasin {suffix}"},
    )
    assert store.status_code == 201, store.text
    reference = f"REGR-REAP-{suffix}"
    draft = client.post(
        f"{API}/part-replenishments",
        headers=storekeeper.headers,
        json={
            "spare_part_store_id": store.json()["spare_part_store_id"],
            "spare_part_id": part.json()["spare_part_id"],
            "quantity": "4",
            "reference": reference,
        },
    )
    assert draft.status_code == 201, draft.text
    replenishment_id = draft.json()["replenishment_id"]

    submitted = client.post(
        f"{API}/part-replenishments/{replenishment_id}/submit", headers=storekeeper.headers
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "SUBMITTED"

    decided = client.post(
        f"{API}/part-replenishments/{replenishment_id}/decision",
        headers=manager.headers,
        json={"action": "APPROVE", "note": "Régression 0064 : la décision doit aboutir."},
    )
    assert decided.status_code == 200, decided.text
    body = decided.json()
    assert body["status"] == "APPROVED"
    assert body["decision_note"] == "Régression 0064 : la décision doit aboutir."
    assert body["decision_by"] is not None and body["decided_at"] is not None
