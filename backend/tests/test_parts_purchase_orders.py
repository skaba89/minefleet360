"""Permissions and site isolation for supplier purchase order drafts."""

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def test_purchase_order_drafts_access_guards(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    keeper = api.user(tenant, "STOREKEEPER", "SITE", "MINE")
    driver = api.user(tenant, "DRIVER", "SITE", "MINE")
    foreign = api.tenant(sites=("OTHER",))
    listed = client.get(f"{API}/parts-purchase-orders", headers=keeper.headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 0
    denied = client.get(f"{API}/parts-purchase-orders", headers=driver.headers)
    assert denied.status_code == 403
    hidden = client.get(
        f"{API}/parts-purchase-orders",
        headers=keeper.headers,
        params={"site_id": str(foreign.sites["OTHER"])},
    )
    assert hidden.status_code == 404
    denied_create = client.post(
        f"{API}/parts-purchase-orders",
        headers=driver.headers,
        json={
            "replenishment_id": "00000000-0000-4000-8000-000000000011",
            "supplier_name": "Fournisseur",
            "supplier_reference": "CMD-1",
        },
    )
    assert denied_create.status_code == 403


def test_purchase_order_cannot_reference_missing_or_foreign_request(client: TestClient, api: Api) -> None:
    """A permitted storekeeper cannot create an order outside their tenant."""
    tenant = api.tenant(sites=("MINE",))
    keeper = api.user(tenant, "STOREKEEPER", "SITE", "MINE")
    foreign = api.tenant(sites=("OTHER",))
    for replenishment_id in (
        "00000000-0000-4000-8000-000000000011",
        str(foreign.sites["OTHER"]),
    ):
        response = client.post(
            f"{API}/parts-purchase-orders",
            headers=keeper.headers,
            json={
                "replenishment_id": replenishment_id,
                "supplier_name": "Fournisseur",
                "supplier_reference": "CMD-ISOLATION",
            },
        )
        assert response.status_code == 404, response.text

    listed = client.get(f"{API}/parts-purchase-orders", headers=keeper.headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 0


def test_purchase_order_rejects_invalid_payload_without_creating_draft(client: TestClient, api: Api) -> None:
    """Malformed IDs and invalid supplier fields must fail validation."""
    tenant = api.tenant(sites=("MINE",))
    keeper = api.user(tenant, "STOREKEEPER", "SITE", "MINE")
    valid = {
        "replenishment_id": "00000000-0000-4000-8000-000000000011",
        "supplier_name": "Fournisseur",
        "supplier_reference": "CMD-VALIDATION",
    }
    invalid = (
        {"replenishment_id": "not-a-uuid"},
        {"supplier_name": ""},
        {"supplier_name": "X" * 201},
        {"supplier_reference": ""},
        {"supplier_reference": "X" * 121},
    )
    for override in invalid:
        response = client.post(
            f"{API}/parts-purchase-orders",
            headers=keeper.headers,
            json={**valid, **override},
        )
        assert response.status_code == 422, response.text

    listed = client.get(f"{API}/parts-purchase-orders", headers=keeper.headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 0
