"""Tenant and role guards for replenishment drafts."""

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
