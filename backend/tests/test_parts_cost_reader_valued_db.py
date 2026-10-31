"""Rapprochement PostgreSQL réel des consommations CMP avec le coût des OT."""

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.db import new_session
from app.core.tenancy import set_tenant_context
from app.maintenance.parts_cost_reader import load_work_order_parts_cost
from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401
from tests.test_maintenance import _report


def test_reader_reconciles_valued_consumption_with_ot(
    client: TestClient,
    api: Api,
    w: World,  # noqa: F811
) -> None:
    keeper = api.user(w.t, "STOREKEEPER", "SITE", "S1")
    vehicle = _vehicle(client, w)
    order_result = _report(client, w, vehicle)
    assert order_result.status_code == 201, order_result.text
    order = order_result.json()

    part_response = client.post(
        f"{API}/parts",
        headers=keeper.headers,
        json={"code": "VALUED-COST-OT-PART", "name": "Filtre", "unit": "EACH"},
    )
    assert part_response.status_code == 201, part_response.text
    part = part_response.json()
    store_response = client.post(
        f"{API}/part-stores",
        headers=keeper.headers,
        json={"site_id": order["site_id"], "code": "VALUED-COST-OT-STORE", "name": "Atelier"},
    )
    assert store_response.status_code == 201, store_response.text
    store = store_response.json()
    stock = {
        "spare_part_store_id": store["spare_part_store_id"],
        "spare_part_id": part["spare_part_id"],
    }

    receipt = client.post(
        f"{API}/part-movements/valued-receipts",
        headers=keeper.headers,
        json={
            **stock,
            "quantity": "3.000",
            "unit_cost": "100.000000",
            "currency": "GNF",
            "reference": "VALUED-COST-OT-RECEIPT",
        },
    )
    assert receipt.status_code == 201, receipt.text
    reservation = client.post(
        f"{API}/part-reservations",
        headers=keeper.headers,
        json={
            **stock,
            "work_order_id": order["work_order_id"],
            "quantity": "2.000",
            "reference": "VALUED-COST-OT-RESERVATION",
        },
    )
    assert reservation.status_code == 201, reservation.text
    consumed = client.post(
        f"{API}/part-reservations/{reservation.json()['spare_part_reservation_id']}/consume",
        headers=keeper.headers,
    )
    assert consumed.status_code == 200, consumed.text

    with new_session() as db:
        set_tenant_context(db, w.t.tenant_id)
        cost, currency = load_work_order_parts_cost(
            db,
            tenant_id=w.t.tenant_id,
            site_id=uuid.UUID(order["site_id"]),
            work_order_id=uuid.UUID(order["work_order_id"]),
        )
        assert cost.known_total == Decimal("200.000000")
        assert cost.valued_movements == 1
        assert cost.unvalued_movements == 0
        assert cost.complete
        assert currency == "GNF"
