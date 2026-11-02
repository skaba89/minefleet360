"""Achats de carburant : la réponse de chaque étape décrit l'objet créé (régression du 404 après commit)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_fuel_pumps import _tank


def test_purchase_lifecycle_responses(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("MINE",))
    ops = api.user(t, "OPS_MANAGER")
    tank = _tank(client, t.admin.headers, t.sites["MINE"])
    supplier = client.post(
        f"{API}/fuel/suppliers",
        headers=t.admin.headers,
        json={"site_id": str(t.sites["MINE"]), "code": "FOURN-1", "name": "Fournisseur fictif"},
    )
    assert supplier.status_code == 201, supplier.text
    created = client.post(
        f"{API}/fuel/purchases",
        headers=t.admin.headers,
        json={
            "fuel_supplier_id": supplier.json()["fuel_supplier_id"],
            "fuel_tank_id": tank["fuel_tank_id"],
            "reference": "BC-REG-1",
            "quantity_liters": "1000.000",
            "unit_price": "12000.00",
            "currency": "GNF",
            "ordered_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    purchase = created.json()
    assert purchase["supplier_code"] == "FOURN-1" and purchase["status"] == "PENDING_APPROVAL"
    pid = purchase["fuel_purchase_order_id"]
    self_decision = client.post(
        f"{API}/fuel/purchases/{pid}/decision", headers=t.admin.headers, json={"decision": "APPROVED"}
    )
    assert self_decision.status_code in (409, 422)
    decided = client.post(
        f"{API}/fuel/purchases/{pid}/decision", headers=ops.headers, json={"decision": "APPROVED"}
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "APPROVED"
    received = client.post(
        f"{API}/fuel/purchases/{pid}/receipts",
        headers=t.admin.headers,
        json={
            "liters": "400.000",
            "delivery_reference": "BL-REG-1",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    assert received.status_code == 201, received.text
    listed = client.get(f"{API}/fuel/purchases", headers=t.admin.headers).json()["items"]
    row = next(p for p in listed if p["fuel_purchase_order_id"] == pid)
    assert Decimal(row["received_liters"]) == Decimal("400")
    assert sum(1 for p in listed if p["reference"] == "BC-REG-1") == 1
