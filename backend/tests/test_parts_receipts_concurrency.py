"""Réceptions simultanées : même référence, une seule augmentation du stock."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def test_concurrent_duplicate_receipts_do_not_double_stock(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    keeper = api.user(tenant, "STOREKEEPER", "SITE", "MINE")
    part_response = client.post(
        f"{API}/parts",
        headers=keeper.headers,
        json={"code": "DUP-RECEIPT-PART", "name": "Filtre", "unit": "EACH"},
    )
    assert part_response.status_code == 201, part_response.text
    part = part_response.json()
    store_response = client.post(
        f"{API}/part-stores",
        headers=keeper.headers,
        json={"site_id": str(tenant.sites["MINE"]), "code": "DUP-RECEIPT-STORE", "name": "Magasin"},
    )
    assert store_response.status_code == 201, store_response.text
    store = store_response.json()
    payload = {
        "spare_part_store_id": store["spare_part_store_id"],
        "spare_part_id": part["spare_part_id"],
        "quantity": "3.000",
        "reference": "DUP-RECEIPT-REFERENCE",
    }
    barrier = Barrier(2)

    def receive(_: int) -> int:
        barrier.wait(timeout=10)
        response = client.post(f"{API}/part-movements/receipts", headers=keeper.headers, json=payload)
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(receive, (1, 2)))
    assert sorted(results) == [201, 409]

    balances = client.get(
        f"{API}/part-balances",
        headers=keeper.headers,
        params={"site_id": str(tenant.sites["MINE"])},
    )
    assert balances.status_code == 200, balances.text
    match = [row for row in balances.json()["items"] if row["spare_part_id"] == part["spare_part_id"]]
    assert len(match) == 1
    assert match[0]["on_hand"] == 3.0
    assert match[0]["reserved"] == 0.0

    movements = client.get(
        f"{API}/part-movements",
        headers=keeper.headers,
        params={"spare_part_id": part["spare_part_id"]},
    )
    assert movements.status_code == 200, movements.text
    assert movements.json()["total"] == 1
    assert movements.json()["items"][0]["reference"] == payload["reference"]
    assert movements.json()["items"][0]["movement_type"] == "RECEIPT"
