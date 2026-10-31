"""Course réelle PostgreSQL : une réservation ne peut être libérée et consommée à la fois."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401
from tests.test_maintenance import _report


def test_release_and_consume_same_reservation_are_exclusive(
    client: TestClient,
    api: Api,
    w: World,  # noqa: F811
) -> None:
    keeper = api.user(w.t, "STOREKEEPER", "SITE", "S1")
    vehicle = _vehicle(client, w)
    order_result = _report(client, w, vehicle)
    assert order_result.status_code == 201, order_result.text
    order = order_result.json()
    part_result = client.post(
        f"{API}/parts",
        headers=keeper.headers,
        json={"code": "RACE-OT-FILTER", "name": "Filtre", "unit": "EACH"},
    )
    assert part_result.status_code == 201, part_result.text
    part = part_result.json()
    store_result = client.post(
        f"{API}/part-stores",
        headers=keeper.headers,
        json={"site_id": order["site_id"], "code": "RACE-OT-STORE", "name": "Atelier"},
    )
    assert store_result.status_code == 201, store_result.text
    store = store_result.json()
    receipt = client.post(
        f"{API}/part-movements/receipts",
        headers=keeper.headers,
        json={
            "spare_part_store_id": store["spare_part_store_id"],
            "spare_part_id": part["spare_part_id"],
            "quantity": "3.000",
            "reference": "RACE-OT-RECEIPT",
        },
    )
    assert receipt.status_code == 201, receipt.text
    reserved = client.post(
        f"{API}/part-reservations",
        headers=keeper.headers,
        json={
            "spare_part_store_id": store["spare_part_store_id"],
            "spare_part_id": part["spare_part_id"],
            "work_order_id": order["work_order_id"],
            "quantity": "2.000",
            "reference": "RACE-OT-RESERVE",
        },
    )
    assert reserved.status_code == 201, reserved.text
    reservation_id = reserved.json()["spare_part_reservation_id"]
    barrier = Barrier(2)

    def transition(action: str) -> int:
        barrier.wait(timeout=10)
        result = client.post(
            f"{API}/part-reservations/{reservation_id}/{action}",
            headers=keeper.headers,
        )
        return result.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(transition, ("release", "consume")))
    assert sorted(codes) == [200, 409]

    rows = client.get(
        f"{API}/part-reservations",
        headers=keeper.headers,
        params={"work_order_id": order["work_order_id"]},
    )
    assert rows.status_code == 200, rows.text
    reservations = [row for row in rows.json()["items"] if row["spare_part_reservation_id"] == reservation_id]
    assert len(reservations) == 1
    assert reservations[0]["status"] in {"CONSUMED", "RELEASED"}

    balances = client.get(
        f"{API}/part-balances",
        headers=keeper.headers,
        params={"site_id": order["site_id"]},
    )
    assert balances.status_code == 200, balances.text
    match = [row for row in balances.json()["items"] if row["spare_part_id"] == part["spare_part_id"]]
    assert len(match) == 1
    assert match[0]["reserved"] == 0.0
    assert match[0]["on_hand"] == (1.0 if reservations[0]["status"] == "CONSUMED" else 3.0)

    movements = client.get(f"{API}/part-movements", headers=keeper.headers)
    assert movements.status_code == 200, movements.text
    related = [row for row in movements.json()["items"] if row["spare_part_id"] == part["spare_part_id"]]
    assert len(related) == (2 if reservations[0]["status"] == "CONSUMED" else 1)
