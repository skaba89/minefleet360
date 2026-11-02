"""Coût complet par engin : composantes, statuts, dénominateurs, portée (docs/LIVRAISON_COUT_COMPLET.md)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import API, Api, TenantFixture
from tests.test_fuel_pumps import _assigned_vehicle_and_driver, _tank


def _work_order_with_labour(
    client: TestClient, api: Api, t: TenantFixture, ops: dict[str, str], vehicle: str, minutes: int
) -> str:
    chief = api.user(t, "WORKSHOP_CHIEF")
    mechanic = api.user(t, "MECHANIC", "SITE", "MINE")
    order = client.post(
        f"{API}/work-orders",
        headers=ops,
        json={"vehicle_id": vehicle, "symptom_code": "ENGINE", "priority": "HIGH"},
    )
    assert order.status_code == 201, order.text
    oid = order.json()["work_order_id"]
    url = f"{API}/work-orders/{oid}"
    for headers, kind, body in (
        (chief.headers, "decision", {"action": "APPROVE"}),
        (chief.headers, "decision", {"action": "ASSIGN", "assigned_to": str(mechanic.user_id)}),
        (mechanic.headers, "progress", {"action": "START"}),
    ):
        version = client.get(url, headers=chief.headers).headers["ETag"]
        done = client.post(f"{url}/{kind}", headers={**headers, "If-Match": version}, json=body)
        assert done.status_code == 200, done.text
    labour = client.post(
        f"{url}/labour",
        headers=mechanic.headers,
        json={"minutes": minutes, "performed_on": date.today().isoformat()},
    )
    assert labour.status_code == 201, labour.text
    return str(oid)


def _consume_valued_part(
    client: TestClient, api: Api, t: TenantFixture, order_id: str, unit_cost: str, currency: str = "GNF"
) -> None:
    keeper = api.user(t, "STOREKEEPER")
    chief = api.user(t, "WORKSHOP_CHIEF")
    part = client.post(
        f"{API}/parts", headers=keeper.headers, json={"code": f"P-{currency}", "name": "Filtre"}
    ).json()
    store = client.post(
        f"{API}/part-stores",
        headers=keeper.headers,
        json={"site_id": str(t.sites["MINE"]), "code": f"MAG-{currency}", "name": "Magasin"},
    ).json()
    stock = {"spare_part_id": part["spare_part_id"], "spare_part_store_id": store["spare_part_store_id"]}
    receipt = client.post(
        f"{API}/part-movements/valued-receipts",
        headers=keeper.headers,
        json={
            **stock,
            "quantity": "4",
            "unit_cost": unit_cost,
            "currency": currency,
            "reference": "BL-PIECES",
        },
    )
    assert receipt.status_code == 201, receipt.text
    reservation = client.post(
        f"{API}/part-reservations",
        headers=chief.headers,
        json={**stock, "work_order_id": order_id, "quantity": "2", "reference": "RES-1"},
    )
    assert reservation.status_code == 201, reservation.text
    consumed = client.post(
        f"{API}/part-reservations/{reservation.json()['spare_part_reservation_id']}/consume",
        headers=chief.headers,
    )
    assert consumed.status_code == 200, consumed.text


def _priced_fuel(
    client: TestClient, api: Api, t: TenantFixture, ops: dict[str, str], unit_price: str
) -> dict:  # type: ignore[type-arg]
    tank = _tank(client, t.admin.headers, t.sites["MINE"])
    supplier = client.post(
        f"{API}/fuel/suppliers",
        headers=t.admin.headers,
        json={"site_id": str(t.sites["MINE"]), "code": "FOURN-1", "name": "Fournisseur fictif"},
    )
    assert supplier.status_code == 201, supplier.text
    supplier_id = supplier.json()["fuel_supplier_id"]
    order = client.post(
        f"{API}/fuel/purchases",
        headers=t.admin.headers,
        json={
            "fuel_supplier_id": supplier_id,
            "fuel_tank_id": tank["fuel_tank_id"],
            "reference": "BC-1",
            "quantity_liters": "1000.000",
            "unit_price": unit_price,
            "currency": "GNF",
            "ordered_at": (datetime.now(UTC) - timedelta(days=3)).isoformat(),
        },
    )
    assert order.status_code == 201, order.text
    oid = order.json()["fuel_purchase_order_id"]
    decided = client.post(f"{API}/fuel/purchases/{oid}/decision", headers=ops, json={"decision": "APPROVED"})
    assert decided.status_code == 200, decided.text
    received = client.post(
        f"{API}/fuel/purchases/{oid}/receipts",
        headers=t.admin.headers,
        json={
            "liters": "1000.000",
            "delivery_reference": "BL-1",
            "occurred_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
        },
    )
    assert received.status_code == 201, received.text
    return tank


def _issue(
    client: TestClient,
    t: TenantFixture,
    ops: dict[str, str],
    tank: dict,
    vehicle: str,
    driver: str,
    meter: str | None,
) -> None:  # type: ignore[type-arg]
    body: dict[str, object] = {
        "fuel_tank_id": tank["fuel_tank_id"],
        "vehicle_id": vehicle,
        "driver_id": driver,
        "liters": "100.000",
        "requested_at": (datetime.now(UTC) - timedelta(hours=5)).isoformat(),
    }
    if meter:
        body.update({"meter_kind": meter, "meter_value": "1000.0"})
    issue = client.post(f"{API}/fuel/issues", headers=ops, json=body)
    assert issue.status_code == 201, issue.text
    approved = client.post(
        f"{API}/fuel/issues/{issue.json()['fuel_issue_id']}/decision",
        headers=t.admin.headers,
        json={"decision": "APPROVED"},
    )
    assert approved.status_code == 200, approved.text


def _meters(client: TestClient, ops: dict[str, str], vehicle: str, kind: str) -> None:
    # Hausse plausible pour le contrôle de vraisemblance des compteurs : 500 km ou 6 h en 8 heures.
    end_value = "1500.0" if kind == "ODOMETER_KM" else "1006.0"
    for hours_ago, value in ((10, "1000.0"), (2, end_value)):
        reading = client.post(
            f"{API}/vehicles/{vehicle}/meter-readings",
            headers=ops,
            json={
                "meter_kind": kind,
                "value": value,
                "read_at": (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat(),
            },
        )
        assert reading.status_code == 201, reading.text


def test_complete_cost_with_estimated_fuel_and_ratios(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("MINE", "PORT"))
    ops, vehicle, driver, meter = _assigned_vehicle_and_driver(client, api, t)
    finance = api.user(t, "FINANCE")
    rate = client.post(
        f"{API}/costs/labour-rates",
        headers=finance.headers,
        json={"hourly_rate": "50000.00", "currency": "GNF", "valid_from": "2026-01-01"},
    )
    assert rate.status_code == 201, rate.text
    duplicate = client.post(
        f"{API}/costs/labour-rates",
        headers=finance.headers,
        json={"hourly_rate": "60000.00", "currency": "GNF", "valid_from": "2026-01-01"},
    )
    assert duplicate.status_code == 409
    tank = _priced_fuel(client, api, t, ops, "12000.00")
    _issue(client, t, ops, tank, vehicle, driver, meter)
    order = _work_order_with_labour(client, api, t, ops, vehicle, 120)
    _consume_valued_part(client, api, t, order, "150000")
    # Compteur porté par la catégorie de l'engin de test (km ou heures) : même règle de calcul.
    kind = "ODOMETER_KM" if meter == "ODOMETER" else "HOUR_METER"
    _meters(client, ops, vehicle, kind)

    resp = client.get(f"{API}/costs/vehicles", headers=finance.headers)
    assert resp.status_code == 200, resp.text
    row = next(v for v in resp.json()["vehicles"] if v["vehicle_id"] == vehicle)
    assert row["fuel"] == {"amount": "1200000.00", "status": "ESTIMATED", "currency": "GNF", "missing": []}
    assert row["labour"]["amount"] == "100000.00" and row["labour"]["status"] == "COMPLETE"
    assert row["parts"]["amount"] == "300000.00" and row["parts"]["status"] == "COMPLETE"
    assert row["tyres"] == {"amount": "0", "status": "COMPLETE", "currency": None, "missing": []}
    assert row["total"] == "1600000.00" and row["total_status"] == "ESTIMATED" and row["currency"] == "GNF"
    measured, ratio, delta = (
        ("km", "cost_per_km", Decimal("500"))
        if kind == "ODOMETER_KM"
        else ("hours", "cost_per_hour", Decimal("6"))
    )
    assert Decimal(row[measured]) == delta
    assert Decimal(row[ratio]) == (Decimal("1600000") / delta).quantize(Decimal("0.01"))
    assert row["tonnes"] == "0.000" and row["cost_per_tonne"] is None and row["cost_per_mission"] is None
    assert resp.json()["vehicles"][0]["vehicle_id"] == vehicle  # classement : le plus coûteux d'abord
    site = next(s for s in resp.json()["sites"] if s["site_id"] == str(t.sites["MINE"]))
    assert site["total"] == "1600000.00"

    history = client.get(
        f"{API}/costs/vehicles/{vehicle}/history", headers=finance.headers, params={"months": 2}
    )
    assert history.status_code == 200, history.text
    months = history.json()["months"]
    assert len(months) == 2 and months[-1]["cost"]["total"] == "1600000.00"


def test_missing_rate_and_unpriced_fuel_are_insufficient(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("MINE",))
    ops, vehicle, driver, meter = _assigned_vehicle_and_driver(client, api, t)
    finance = api.user(t, "FINANCE")
    tank = _tank(client, t.admin.headers, t.sites["MINE"])
    receipt = client.post(
        f"{API}/fuel/tanks/{tank['fuel_tank_id']}/receipts",
        headers=t.admin.headers,
        json={
            "liters": "500.000",
            "reference": "BL-SANS-PRIX",
            "occurred_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
    )
    assert receipt.status_code == 201, receipt.text
    _issue(client, t, ops, tank, vehicle, driver, meter)
    _work_order_with_labour(client, api, t, ops, vehicle, 60)
    row = next(
        v
        for v in client.get(f"{API}/costs/vehicles", headers=finance.headers).json()["vehicles"]
        if v["vehicle_id"] == vehicle
    )
    assert row["fuel"]["status"] == "INSUFFICIENT" and row["fuel"]["amount"] is None
    assert row["labour"]["status"] == "INSUFFICIENT"
    assert row["total"] is None and row["total_status"] == "INSUFFICIENT"
    assert "taux horaire de main-d'œuvre" in row["missing"]
    assert any("prix d'achat du carburant" in m for m in row["missing"])
    assert row["cost_per_km"] is None


def test_mixed_currencies_are_never_summed(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("MINE",))
    ops, vehicle, _, _ = _assigned_vehicle_and_driver(client, api, t)
    finance = api.user(t, "FINANCE")
    client.post(
        f"{API}/costs/labour-rates",
        headers=finance.headers,
        json={"hourly_rate": "40000.00", "currency": "GNF", "valid_from": "2026-01-01"},
    )
    order = _work_order_with_labour(client, api, t, ops, vehicle, 60)
    _consume_valued_part(client, api, t, order, "10", currency="USD")
    row = next(
        v
        for v in client.get(f"{API}/costs/vehicles", headers=finance.headers).json()["vehicles"]
        if v["vehicle_id"] == vehicle
    )
    assert row["parts"]["currency"] == "USD" and row["labour"]["currency"] == "GNF"
    assert row["total"] is None and row["total_status"] == "INSUFFICIENT"
    assert "devises multiples sans conversion" in row["missing"]


def test_scope_permissions_and_validation(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("MINE", "PORT"))
    _, vehicle, _, _ = _assigned_vehicle_and_driver(client, api, t)
    port_finance = api.user(t, "FINANCE", "SITE", "PORT")
    listed = client.get(f"{API}/costs/vehicles", headers=port_finance.headers).json()
    assert vehicle not in {v["vehicle_id"] for v in listed["vehicles"]}
    assert (
        client.get(f"{API}/costs/vehicles/{vehicle}/history", headers=port_finance.headers).status_code == 404
    )
    assert (
        client.get(
            f"{API}/costs/vehicles", headers=port_finance.headers, params={"site_id": str(t.sites["MINE"])}
        ).status_code
        == 404
    )
    tenant_rate = client.post(
        f"{API}/costs/labour-rates",
        headers=port_finance.headers,
        json={"hourly_rate": "1.00", "currency": "GNF", "valid_from": "2026-01-01"},
    )
    assert tenant_rate.status_code == 403
    site_rate = client.post(
        f"{API}/costs/labour-rates",
        headers=port_finance.headers,
        json={
            "site_id": str(t.sites["PORT"]),
            "hourly_rate": "1.00",
            "currency": "GNF",
            "valid_from": "2026-01-01",
        },
    )
    assert site_rate.status_code == 201
    other = api.tenant(sites=("MINE",))
    other_finance = api.user(other, "FINANCE")
    assert (
        client.get(f"{API}/costs/vehicles/{vehicle}/history", headers=other_finance.headers).status_code
        == 404
    )
    assert vehicle not in {
        v["vehicle_id"]
        for v in client.get(f"{API}/costs/vehicles", headers=other_finance.headers).json()["vehicles"]
    }
    dispatcher = api.user(t, "DISPATCHER", "SITE", "MINE")
    assert client.get(f"{API}/costs/vehicles", headers=dispatcher.headers).status_code == 403
    finance = api.user(t, "FINANCE")
    now = datetime.now(UTC)
    inverted = client.get(
        f"{API}/costs/vehicles",
        headers=finance.headers,
        params={"from": now.isoformat(), "to": (now - timedelta(days=1)).isoformat()},
    )
    assert inverted.status_code == 422
    too_long = client.get(
        f"{API}/costs/vehicles",
        headers=finance.headers,
        params={"from": (now - timedelta(days=400)).isoformat()},
    )
    assert too_long.status_code == 422


def test_tyre_cost_is_estimated_per_km_on_vehicle(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("MINE",))
    _, vehicle, _, _ = _assigned_vehicle_and_driver(client, api, t)
    chief = api.user(t, "WORKSHOP_CHIEF")
    finance = api.user(t, "FINANCE")
    tyre = client.post(
        f"{API}/tyres",
        headers=chief.headers,
        json={
            "site_id": str(t.sites["MINE"]),
            "serial_number": "SN-COUT-1",
            "brand": "MarqueFictive",
            "model": "M",
            "size": "27.00R49",
            "category": "DRIVE",
            "purchase_cost": "1000000.00",
            "currency": "GNF",
            "initial_tread_mm": "80.0",
            "scrap_tread_mm": "10.0",
        },
    ).json()
    url = f"{API}/tyres/{tyre['tyre_id']}"
    for path, body in (
        ("mount", {"vehicle_id": vehicle, "position_code": "AV-G", "odometer_km": "1000"}),
        ("inspections", {"tread_mm": "70.0", "odometer_km": "1400"}),
    ):
        version = client.get(url, headers=chief.headers).headers["ETag"]
        done = client.post(f"{url}/{path}", headers={**chief.headers, "If-Match": version}, json=body)
        assert done.status_code == 200, done.text
    row = next(
        v
        for v in client.get(f"{API}/costs/vehicles", headers=finance.headers).json()["vehicles"]
        if v["vehicle_id"] == vehicle
    )
    # 400 km mesurés, tout le kilométrage connu du pneu : amortissement estimé = coût total du pneu.
    assert row["tyres"] == {"amount": "1000000.00", "status": "ESTIMATED", "currency": "GNF", "missing": []}
    assert Decimal(row["total"]) == Decimal("1000000.00") and row["total_status"] == "ESTIMATED"
