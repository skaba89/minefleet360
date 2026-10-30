"""Réceptions de pièces : stock, idempotence, autorisations et isolation."""

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def test_receive_parts_updates_balance_once(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    keeper = api.user(tenant, "STOREKEEPER", "SITE", "MINE")
    driver = api.user(tenant, "DRIVER", "SITE", "MINE")
    part = client.post(
        f"{API}/parts",
        headers=keeper.headers,
        json={"code": "FILTRE-REC", "name": "Filtre", "unit": "EACH"},
    ).json()
    store = client.post(
        f"{API}/part-stores",
        headers=keeper.headers,
        json={"site_id": str(tenant.sites["MINE"]), "code": "STOCK-REC", "name": "Magasin"},
    ).json()
    payload = {
        "spare_part_store_id": store["spare_part_store_id"],
        "spare_part_id": part["spare_part_id"],
        "quantity": "3.500",
        "reference": "LIVRAISON-001",
    }
    created = client.post(f"{API}/part-movements/receipts", headers=keeper.headers, json=payload)
    assert created.status_code == 201, created.text
    response = client.post(f"{API}/part-movements/receipts", headers=keeper.headers, json=payload)
    assert response.status_code == 409
    response = client.post(f"{API}/part-movements/receipts", headers=driver.headers, json=payload)
    assert response.status_code == 403
    balance = client.get(f"{API}/part-balances", headers=keeper.headers).json()
    assert balance["total"] == 1
    assert balance["items"][0]["on_hand"] == 3.5

    outsider = api.tenant(sites=("OTHER",))
    outsider_part = client.post(
        f"{API}/parts",
        headers=api.user(outsider, "STOREKEEPER", "SITE", "OTHER").headers,
        json={"code": "OTHER-PART", "name": "Etranger", "unit": "EACH"},
    ).json()
    foreign = {**payload, "spare_part_id": outsider_part["spare_part_id"], "reference": "FOREIGN"}
    response = client.post(f"{API}/part-movements/receipts", headers=keeper.headers, json=foreign)
    assert response.status_code == 422
