"""Deux réservations parallèles ne peuvent dépasser le disponible (PostgreSQL réel)."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401
from tests.test_maintenance import _report


def test_concurrent_reservations_do_not_overbook(client: TestClient, api: Api, w: World) -> None:  # noqa: F811
    keeper = api.user(w.t, "STOREKEEPER", "SITE", "S1")
    vehicle = _vehicle(client, w)
    order_response = _report(client, w, vehicle)
    assert order_response.status_code == 201, order_response.text
    order = order_response.json()

    part_response = client.post(
        f"{API}/parts",
        headers=keeper.headers,
        json={"code": "PARALLEL-FILTER", "name": "Filtre", "unit": "EACH"},
    )
    assert part_response.status_code == 201, part_response.text
    part = part_response.json()
    store_response = client.post(
        f"{API}/part-stores",
        headers=keeper.headers,
        json={"site_id": order["site_id"], "code": "PARALLEL-STORE", "name": "Magasin"},
    )
    assert store_response.status_code == 201, store_response.text
    store = store_response.json()
    stock = {
        "spare_part_store_id": store["spare_part_store_id"],
        "spare_part_id": part["spare_part_id"],
    }
    receipt = client.post(
        f"{API}/part-movements/receipts",
        headers=keeper.headers,
        json={**stock, "quantity": "3.000", "reference": "PARALLEL-RECEIPT"},
    )
    assert receipt.status_code == 201, receipt.text
    barrier = Barrier(2)

    def reserve(index: int) -> int:
        barrier.wait(timeout=10)
        response = client.post(
            f"{API}/part-reservations",
            headers=keeper.headers,
            json={
                **stock,
                "work_order_id": order["work_order_id"],
                "quantity": "2.000",
                "reference": f"PARALLEL-RESERVE-{index}",
            },
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(reserve, (1, 2)))
    assert sorted(codes) == [201, 409]

    balances = client.get(f"{API}/part-balances", headers=keeper.headers, params={"site_id": order["site_id"]})
    assert balances.status_code == 200, balances.text
    match = [row for row in balances.json()["items"] if row["spare_part_id"] == part["spare_part_id"]]
    assert len(match) == 1
    assert match[0]["on_hand"] == 3.0
    assert match[0]["reserved"] == 2.0

    reservations = client.get(
        f"{API}/part-reservations",
        headers=keeper.headers,
        params={"work_order_id": order["work_order_id"]},
    )
    assert reservations.status_code == 200, reservations.text
    related = [row for row in reservations.json()["items"] if row["spare_part_id"] == part["spare_part_id"]]
    assert len(related) == 1
    assert related[0]["status"] == "ACTIVE"
