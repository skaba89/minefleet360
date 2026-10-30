"""Tests de lecture du catalogue et des magasins avec séparation tenant/site."""

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def test_parts_read_endpoints_and_permissions(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    storekeeper = api.user(tenant, "STOREKEEPER", "SITE", "MINE")
    unauthorized = api.user(tenant, "DRIVER", "SITE", "MINE")

    for path in ("/parts", "/part-stores", "/part-balances"):
        response = client.get(f"{API}{path}", headers=storekeeper.headers)
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 0
        denied = client.get(f"{API}{path}", headers=unauthorized.headers)
        assert denied.status_code == 403

    outsider = api.tenant(sites=("OTHER",))
    hidden = client.get(
        f"{API}/part-stores",
        headers=storekeeper.headers,
        params={"site_id": str(outsider.sites["OTHER"])},
    )
    assert hidden.status_code == 404
    hidden_stock = client.get(
        f"{API}/part-balances",
        headers=storekeeper.headers,
        params={"site_id": str(outsider.sites["OTHER"])},
    )
    assert hidden_stock.status_code == 404
