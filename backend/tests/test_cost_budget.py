"""Budget prévisionnel et écarts site × mois × composante (contrôle de gestion, tranche 1)."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import API, Api, TenantFixture
from tests.test_costs import _consume_valued_part, _issue, _priced_fuel, _work_order_with_labour
from tests.test_fuel_pumps import _assigned_vehicle_and_driver


def _month(offset: int = 0) -> str:
    today = datetime.now(UTC).date().replace(day=1)
    for _ in range(abs(offset)):
        today = (
            (today + timedelta(days=32)).replace(day=1)
            if offset > 0
            else (today - timedelta(days=1)).replace(day=1)
        )
    return today.strftime("%Y-%m")


def _budget(client: TestClient, headers: dict[str, str], t: TenantFixture, **body: object):  # type: ignore[no-untyped-def]
    payload = {"site_id": str(t.sites["MINE"]), "month": _month(), "currency": "GNF", **body}
    return client.post(f"{API}/costs/budgets", headers=headers, json=payload)


def test_budget_variance_against_actual_complete_cost(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("MINE",))
    ops, vehicle, driver, meter = _assigned_vehicle_and_driver(client, api, t)
    finance = api.user(t, "FINANCE")
    rate = client.post(
        f"{API}/costs/labour-rates",
        headers=finance.headers,
        json={"hourly_rate": "50000.00", "currency": "GNF", "valid_from": "2026-01-01"},
    )
    assert rate.status_code == 201, rate.text
    tank = _priced_fuel(client, api, t, ops, "12000.00")
    _issue(client, t, ops, tank, vehicle, driver, meter)  # carburant estimé 1 200 000 GNF
    order = _work_order_with_labour(client, api, t, ops, vehicle, 120)  # main-d'œuvre 100 000 GNF
    _consume_valued_part(client, api, t, order, "150000")  # pièces 300 000 GNF

    assert _budget(client, finance.headers, t, component="FUEL", amount="1000000.00").status_code == 201
    assert _budget(client, finance.headers, t, component="PARTS", amount="400000.00").status_code == 201
    revised = _budget(
        client, finance.headers, t, component="PARTS", amount="300000.00", note="Révision fictive"
    )
    assert revised.status_code == 201, revised.text
    assert (
        _budget(client, finance.headers, t, component="LABOUR", amount="40.00", currency="USD").status_code
        == 201
    )
    assert (
        _budget(client, finance.headers, t, component="FUEL", amount="900000.00", month=_month(1)).status_code
        == 201
    )

    resp = client.get(
        f"{API}/costs/budget-variance", headers=finance.headers, params={"from": _month(), "to": _month(1)}
    )
    assert resp.status_code == 200, resp.text
    rows = {
        (r["month"], r["component"]): r for r in resp.json()["rows"] if r["site_id"] == str(t.sites["MINE"])
    }
    fuel = rows[(_month(), "FUEL")]
    assert (fuel["actual_amount"], fuel["actual_status"]) == ("1200000.00", "ESTIMATED")
    assert (fuel["variance_amount"], fuel["variance_percent"]) == ("200000.00", "20.00")
    parts = rows[(_month(), "PARTS")]
    assert parts["budget_amount"] == "300000.00"  # la version la plus récente fait foi
    assert parts["variance_amount"] == "0.00"
    labour = rows[(_month(), "LABOUR")]
    assert (
        labour["variance_amount"] is None
        and labour["not_comparable_reason"] == "devises différentes : aucune conversion"
    )
    tyres = rows[(_month(), "TYRES")]
    assert tyres["budget_amount"] is None and tyres["not_comparable_reason"] == "aucun budget saisi"
    future = rows[(_month(1), "FUEL")]
    assert future["actual_status"] == "FUTURE" and future["variance_amount"] is None

    # Chaque version est journalisée (ajout seul : aucune révision n'écrase la précédente).
    audit = client.get(
        f"{API}/audit-events",
        headers=t.admin.headers,
        params={"action": "cost.budget.create", "page_size": 50},
    ).json()["items"]
    assert len(audit) == 5


def test_budget_permissions_scope_and_validation(client: TestClient, api: Api) -> None:
    t, other = api.tenant(sites=("MINE", "PORT")), api.tenant(sites=("MINE",))
    finance = api.user(t, "FINANCE")
    for role in ("OPS_MANAGER", "AUDITOR", "DIRECTION"):
        reader = api.user(t, role)
        assert client.get(f"{API}/costs/budget-variance", headers=reader.headers).status_code == 200, role
        assert _budget(client, reader.headers, t, component="FUEL", amount="1.00").status_code in (
            201 if role == "DIRECTION" else 403,
        ), role
    for role in ("WORKSHOP_CHIEF", "HSE", "TENANT_ADMIN"):
        account = api.user(t, role) if role != "TENANT_ADMIN" else t.admin
        assert client.get(f"{API}/costs/budget-variance", headers=account.headers).status_code == 403, role
    # Finance d'un seul site : pas de budget pour un autre site.
    site_finance = api.user(t, "FINANCE", "SITE", "MINE")
    refused = _budget(
        client, site_finance.headers, t, component="FUEL", amount="1.00", site_id=str(t.sites["PORT"])
    )
    assert refused.status_code == 422 and refused.json()["code"] == "REFERENCE_NOT_FOUND"
    # Site d'un autre tenant : indiscernable d'un site inexistant.
    foreign = _budget(
        client, finance.headers, t, component="FUEL", amount="1.00", site_id=str(other.sites["MINE"])
    )
    assert foreign.status_code == 422 and foreign.json()["code"] == "REFERENCE_NOT_FOUND"
    # Validations : composante, mois, montant, devise, période.
    assert _budget(client, finance.headers, t, component="RENT", amount="1.00").status_code == 422
    assert (
        _budget(client, finance.headers, t, component="FUEL", amount="1.00", month="2026-13").status_code
        == 422
    )
    assert _budget(client, finance.headers, t, component="FUEL", amount="-1.00").status_code == 422
    assert (
        _budget(client, finance.headers, t, component="FUEL", amount="1.00", currency="gnf").status_code
        == 422
    )
    too_long = client.get(
        f"{API}/costs/budget-variance", headers=finance.headers, params={"from": "2025-01", "to": "2026-06"}
    )
    assert too_long.status_code == 422
    inverted = client.get(
        f"{API}/costs/budget-variance", headers=finance.headers, params={"from": "2026-06", "to": "2026-01"}
    )
    assert inverted.status_code == 422
