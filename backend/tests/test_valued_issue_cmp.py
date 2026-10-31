"""Une sortie valorisée conserve le CMP et les invariants de stock."""

from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401
from tests.test_maintenance import _report


def test_cmp_issue_reduces_quantity_and_value(client: TestClient, api: Api, w: World) -> None:  # noqa: F811
    keeper = api.user(w.t, "STOREKEEPER", "SITE", "S1")
    order = _report(client, w, _vehicle(client, w))
    assert order.status_code == 201, order.text
    part = client.post(
        f"{API}/parts",
        headers=keeper.headers,
        json={"code": "CMP-ISSUE-PART", "name": "Filtre", "unit": "EACH"},
    )
    assert part.status_code == 201, part.text
    store = client.post(
        f"{API}/part-stores",
        headers=keeper.headers,
        json={
            "site_id": order.json()["site_id"],
            "code": "CMP-ISSUE-STORE",
            "name": "Magasin",
        },
    )
    assert store.status_code == 201, store.text
    stock = {
        "spare_part_id": part.json()["spare_part_id"],
        "spare_part_store_id": store.json()["spare_part_store_id"],
    }
    receipt = client.post(
        f"{API}/part-movements/valued-receipts",
        headers=keeper.headers,
        json={**stock, "quantity": "3", "unit_cost": "100", "currency": "GNF", "reference": "CMP-IN"},
    )
    assert receipt.status_code == 201, receipt.text
    issue = client.post(
        f"{API}/part-movements/valued-issues",
        headers=keeper.headers,
        json={**stock, "quantity": "2", "reference": "CMP-OUT"},
    )
    assert issue.status_code == 201, issue.text
    assert Decimal(issue.json()["total_cost"]) == Decimal("200")
    assert Decimal(issue.json()["unit_cost"]) == Decimal("100")
    assert issue.json()["valuation_currency"] == "GNF"
    duplicate = client.post(
        f"{API}/part-movements/valued-issues",
        headers=keeper.headers,
        json={**stock, "quantity": "1", "reference": "CMP-OUT"},
    )
    assert duplicate.status_code == 409, duplicate.text
    balances = client.get(f"{API}/part-balances", headers=keeper.headers)
    assert balances.status_code == 200
    matching = [
        item
        for item in balances.json()["items"]
        if item["spare_part_id"] == stock["spare_part_id"]
    ]
    assert len(matching) == 1
    assert Decimal(str(matching[0]["on_hand"])) == Decimal("1")
