"""Tests PostgreSQL réels : deux écritures concurrentes ne peuvent surconsommer."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def test_concurrent_stock_issues_do_not_overdraw(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    keeper = api.user(tenant, "STOREKEEPER", "SITE", "MINE")
    part_response = client.post(
        f"{API}/parts",
        headers=keeper.headers,
        json={"code": "PART-RACE", "name": "Filtre", "unit": "EACH"},
    )
    assert part_response.status_code == 201, part_response.text
    part = part_response.json()
    store_response = client.post(
        f"{API}/part-stores",
        headers=keeper.headers,
        json={"site_id": str(tenant.sites["MINE"]), "code": "RACE-STORE", "name": "Magasin"},
    )
    assert store_response.status_code == 201, store_response.text
    store = store_response.json()
    payload = {
        "spare_part_store_id": store["spare_part_store_id"],
        "spare_part_id": part["spare_part_id"],
        "quantity": "3.000",
        "reference": "RACE-RECEIPT",
    }
    receipt = client.post(f"{API}/part-movements/receipts", headers=keeper.headers, json=payload)
    assert receipt.status_code == 201, receipt.text

    barrier = Barrier(2)

    def issue(index: int) -> int:
        barrier.wait(timeout=10)
        response = client.post(
            f"{API}/part-movements/issues",
            headers=keeper.headers,
            json={**payload, "quantity": "2.000", "reference": f"RACE-ISSUE-{index}"},
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(issue, (1, 2)))
    assert sorted(results) == [201, 409]

    balances = client.get(
        f"{API}/part-balances",
        headers=keeper.headers,
        params={"site_id": str(tenant.sites["MINE"])},
    )
    assert balances.status_code == 200, balances.text
    actual = [row for row in balances.json()["items"] if row["spare_part_id"] == part["spare_part_id"]]
    assert len(actual) == 1
    assert actual[0]["on_hand"] == 1.0
    assert actual[0]["reserved"] == 0.0

    movements = client.get(
        f"{API}/part-movements",
        headers=keeper.headers,
        params={"spare_part_id": part["spare_part_id"]},
    )
    assert movements.status_code == 200, movements.text
    assert movements.json()["total"] == 2
    assert sorted(row["movement_type"] for row in movements.json()["items"]) == ["ISSUE", "RECEIPT"]
