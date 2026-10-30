"""Réservation de pièces : solde disponible et protections multi-tenant."""

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401
from tests.test_maintenance import _report


def test_reserve_parts_for_work_order(client: TestClient, api: Api, w: World) -> None:  # noqa: F811
    keeper = api.user(w.t, "STOREKEEPER", "SITE", "S1")
    vehicle = _vehicle(client, w)
    order_result = _report(client, w, vehicle)
    assert order_result.status_code == 201, order_result.text
    order = order_result.json()
    part = client.post(
        f"{API}/parts",
        headers=keeper.headers,
        json={"code": "OT-FILTRE", "name": "Filtre", "unit": "EACH"},
    ).json()
    store_response = client.post(
        f"{API}/part-stores",
        headers=keeper.headers,
        json={"site_id": order["site_id"], "code": "OT-MAG", "name": "Atelier"},
    )
    assert store_response.status_code == 201, store_response.text
    store = store_response.json()
    data = {
        "spare_part_store_id": store["spare_part_store_id"],
        "spare_part_id": part["spare_part_id"],
        "work_order_id": order["work_order_id"],
        "quantity": "2.000",
        "reference": "OT-RES-001",
    }
    endpoint = f"{API}/part-reservations"
    assert client.post(endpoint, headers=keeper.headers, json=data).status_code == 409
    receipt = {
        "spare_part_store_id": store["spare_part_store_id"],
        "spare_part_id": part["spare_part_id"],
        "quantity": "3.000",
        "reference": "OT-DELIVERY",
    }
    assert client.post(
        f"{API}/part-movements/receipts", headers=keeper.headers, json=receipt
    ).status_code == 201
    reserved = client.post(endpoint, headers=keeper.headers, json=data)
    assert reserved.status_code == 201, reserved.text
    assert reserved.json()["status"] == "ACTIVE"
    assert client.post(endpoint, headers=keeper.headers, json=data).status_code == 409
    more = {**data, "reference": "OT-RES-002", "quantity": "2.000"}
    assert client.post(endpoint, headers=keeper.headers, json=more).status_code == 409
    balances = client.get(f"{API}/part-balances", headers=keeper.headers).json()
    assert balances["items"][0]["on_hand"] == 3.0
    assert balances["items"][0]["reserved"] == 2.0
