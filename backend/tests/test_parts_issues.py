"""Tests de sortie atomique et du contrôle du stock disponible."""

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def test_issue_prevents_negative_balance_and_duplicates(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    keeper = api.user(tenant, "STOREKEEPER", "SITE", "MINE")
    driver = api.user(tenant, "DRIVER", "SITE", "MINE")
    part = client.post(
        f"{API}/parts",
        headers=keeper.headers,
        json={"code": "PART-ISSUE", "name": "Filtre", "unit": "EACH"},
    ).json()
    store = client.post(
        f"{API}/part-stores",
        headers=keeper.headers,
        json={"site_id": str(tenant.sites["MINE"]), "code": "ISSUE-ST", "name": "Magasin"},
    ).json()
    payload = {
        "spare_part_store_id": store["spare_part_store_id"],
        "spare_part_id": part["spare_part_id"],
        "quantity": "2.000",
        "reference": "ISSUE-001",
    }
    endpoint = f"{API}/part-movements/issues"
    assert client.post(endpoint, headers=keeper.headers, json=payload).status_code == 409
    receipt = {**payload, "quantity": "3.000", "reference": "RECEIPT-001"}
    received = client.post(f"{API}/part-movements/receipts", headers=keeper.headers, json=receipt)
    assert received.status_code == 201, received.text
    issued = client.post(endpoint, headers=keeper.headers, json=payload)
    assert issued.status_code == 201, issued.text
    assert client.post(endpoint, headers=keeper.headers, json=payload).status_code == 409
    too_much = {**payload, "quantity": "2.000", "reference": "ISSUE-002"}
    assert client.post(endpoint, headers=keeper.headers, json=too_much).status_code == 409
    assert client.post(endpoint, headers=driver.headers, json=too_much).status_code == 403
    balances = client.get(f"{API}/part-balances", headers=keeper.headers).json()
    assert balances["items"][0]["on_hand"] == 1.0
