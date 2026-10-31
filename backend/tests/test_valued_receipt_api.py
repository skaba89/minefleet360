"""Réception valorisée via API avec autorisations et comptabilisation."""

from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def test_valued_receipt_api_returns_financial_movement(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    keeper = api.user(tenant, "STOREKEEPER", "SITE", "MINE")
    part = client.post(
        f"{API}/parts",
        headers=keeper.headers,
        json={"code": "VALUED-API-PART", "name": "Filtre", "unit": "EACH"},
    )
    assert part.status_code == 201, part.text
    store = client.post(
        f"{API}/part-stores",
        headers=keeper.headers,
        json={"site_id": str(tenant.sites["MINE"]), "code": "VALUED-API-STORE", "name": "Magasin"},
    )
    assert store.status_code == 201, store.text
    payload = {
        "spare_part_store_id": store.json()["spare_part_store_id"],
        "spare_part_id": part.json()["spare_part_id"],
        "quantity": "3",
        "unit_cost": "100",
        "currency": "GNF",
        "reference": "VALUED-API-INVOICE-1",
    }
    receipt = client.post(f"{API}/part-movements/valued-receipts", headers=keeper.headers, json=payload)
    assert receipt.status_code == 201, receipt.text
    data = receipt.json()
    assert Decimal(str(data["total_cost"])) == Decimal("300")
    assert Decimal(str(data["unit_cost"])) == Decimal("100")
    assert data["valuation_currency"] == "GNF"
    duplicate = client.post(f"{API}/part-movements/valued-receipts", headers=keeper.headers, json=payload)
    assert duplicate.status_code == 409
