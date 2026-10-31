"""Les sorties historiques sans prix ne peuvent pas diminuer un stock valorisé."""

from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401
from tests.test_maintenance import _report


def test_unpriced_issue_and_consumption_rejected_for_valued_balance(
    client: TestClient,
    api: Api,
    w: World,  # noqa: F811
) -> None:
    keeper = api.user(w.t, "STOREKEEPER", "SITE", "S1")
    order_response = _report(client, w, _vehicle(client, w))
    assert order_response.status_code == 201, order_response.text
    order = order_response.json()
    part = client.post(
        f"{API}/parts",
        headers=keeper.headers,
        json={"code": "PROTECT-ISSUE-PART", "name": "Filtre", "unit": "EACH"},
    )
    assert part.status_code == 201, part.text
    store = client.post(
        f"{API}/part-stores",
        headers=keeper.headers,
        json={"site_id": order["site_id"], "code": "PROTECT-ISSUE-STORE", "name": "Magasin"},
    )
    assert store.status_code == 201, store.text
    stock = {
        "spare_part_id": part.json()["spare_part_id"],
        "spare_part_store_id": store.json()["spare_part_store_id"],
    }
    valued = client.post(
        f"{API}/part-movements/valued-receipts",
        headers=keeper.headers,
        json={**stock, "quantity": "3", "unit_cost": "100", "currency": "GNF", "reference": "PV-001"},
    )
    assert valued.status_code == 201, valued.text
    issue = client.post(
        f"{API}/part-movements/issues",
        headers=keeper.headers,
        json={**stock, "quantity": "1", "reference": "PV-ISSUE"},
    )
    assert issue.status_code == 409, issue.text
    reserved = client.post(
        f"{API}/part-reservations",
        headers=keeper.headers,
        json={**stock, "quantity": "1", "reference": "PV-RES", "work_order_id": order["work_order_id"]},
    )
    assert reserved.status_code == 201, reserved.text
    consumed = client.post(
        f"{API}/part-reservations/{reserved.json()['spare_part_reservation_id']}/consume",
        headers=keeper.headers,
    )
    assert consumed.status_code == 409, consumed.text
    balances = client.get(f"{API}/part-balances", headers=keeper.headers)
    assert balances.status_code == 200
    matching = [item for item in balances.json()["items"] if item["spare_part_id"] == stock["spare_part_id"]]
    assert len(matching) == 1
    assert Decimal(str(matching[0]["on_hand"])) == Decimal("3")
    assert Decimal(str(matching[0]["reserved"])) == Decimal("1")
