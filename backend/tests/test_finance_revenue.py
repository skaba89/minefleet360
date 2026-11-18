"""Revenus par contrat (tarif × quantité mesurée) et marge par site (contrôle de gestion, tranche 3)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_assignment import World, w  # noqa: F401  (fixture w)
from tests.test_contract_tariffs import _approve, _contract
from tests.test_dispatch import _assignment, _event, _now, _refs
from tests.test_weighing import _ticket, _weighbridge

FULL_TRIP = ("DEPARTED", "ARRIVED_LOADING", "LOADED", "ARRIVED_UNLOADING", "UNLOADED", "COMPLETED")


def _billable(client: TestClient, w: World, api: Api, tariff: dict[str, str] | None) -> str:  # noqa: F811
    contract = _contract(client, w.t, site="S1")
    _approve(w.t, contract, api.user(w.t, "DIRECTION"))
    if tariff is not None:
        finance = api.user(w.t, "FINANCE")
        body = {"contract_id": contract, "currency": "GNF", "valid_from": "2026-01-01", **tariff}
        resp = client.post(f"{API}/contract-tariffs", headers=finance.headers, json=body)
        assert resp.status_code == 201, resp.text
    return contract


def _trip(
    client: TestClient,
    w: World,  # noqa: F811
    contract: str | None,
    *,
    weigh: dict[str, str] | None = None,
    until: str = "COMPLETED",
) -> str:
    assignment = _assignment(client, w)
    refs = _refs(client, w)
    created = client.post(
        f"{API}/missions",
        headers=w.ops.headers,
        json={
            "vehicle_assignment_id": assignment["vehicle_assignment_id"],
            "origin_location_id": refs["origin"],
            "destination_location_id": refs["destination"],
            "material_id": refs["material"],
            "planned_start": _now().isoformat(),
            "contract_id": contract,
        },
    )
    assert created.status_code == 201, created.text
    mid = created.json()["mission_id"]
    for event in FULL_TRIP[: FULL_TRIP.index(until) + 1]:
        if event == "ARRIVED_UNLOADING" and weigh is not None:
            rotation = client.get(f"{API}/missions/{mid}", headers=w.ops.headers).json()["rotations"][0]
            ticket = client.post(
                f"{API}/weighing-tickets",
                headers=w.ops.headers,
                json=_ticket(rotation["rotation_id"], _weighbridge(client, w), **weigh),
            )
            assert ticket.status_code == 201, ticket.text
        resp = _event(client, w, mid, event)
        assert resp.status_code == 200, (event, resp.text)
    return str(mid)


def _report(client: TestClient, headers: dict[str, str]) -> dict:  # type: ignore[type-arg]
    resp = client.get(f"{API}/finance/revenue", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()  # type: ignore[no-any-return]


def test_revenue_per_measured_tonne_and_site_margin(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    contract = _billable(client, w, api, {"basis": "TONNE", "unit_price": "25000.0000"})
    _trip(client, w, contract, weigh={})  # pesée valide : 52 000 − 18 000 kg = 34 t
    _trip(  # saisie dégradée non approuvée : exclue et signalée
        client, w, contract, weigh={"source": "MANUAL_DEGRADED", "degraded_reason": "WEIGHBRIDGE_DOWN"}
    )
    _trip(client, w, None)  # mission sans contrat : revenu inconnu

    report = _report(client, api.user(w.t, "FINANCE").headers)
    row = next(c for c in report["contracts"] if c["contract_id"] == contract)
    assert (row["amount"], row["currency"], row["tonnes"]) == ("850000.00", "GNF", "34.000")
    assert row["status"] == "PARTIAL" and row["missions_completed"] == 2
    assert "pesée dégradée en attente d'approbation (exclue)" in row["missing"]
    site = next(s for s in report["sites"] if s["site_id"] == str(w.t.sites["S1"]))
    assert site["revenue"] == "850000.00" and site["missions_without_contract"] == 1
    if site["margin"] is not None:
        cost = site["cost"] or "0"
        assert float(site["margin"]) == float(site["revenue"]) - float(cost)
        assert "sans contrat" in site["not_comparable_reason"]


def test_flat_fee_unmeasured_basis_missing_tariff_and_access(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    flat = _billable(client, w, api, {"basis": "MISSION", "unit_price": "500000.0000"})
    hourly = _billable(client, w, api, {"basis": "HOUR", "unit_price": "350000.0000"})
    untariffed = _billable(client, w, api, None)
    for contract in (flat, hourly, untariffed):
        _trip(client, w, contract)
    _trip(client, w, flat, until="LOADED")  # mission non terminée : aucun forfait

    report = _report(client, api.user(w.t, "DIRECTION").headers)
    rows = {c["contract_id"]: c for c in report["contracts"]}
    assert (rows[flat]["amount"], rows[flat]["status"], rows[flat]["missions_completed"]) == (
        "500000.00",
        "COMPLETE",
        1,
    )
    # Heures moteur non mesurées par mission : aucun revenu inventé.
    assert rows[hourly]["amount"] is None and rows[hourly]["status"] == "INSUFFICIENT"
    assert any("HOUR" in m for m in rows[hourly]["missing"])
    assert rows[untariffed]["amount"] is None and rows[untariffed]["status"] == "INSUFFICIENT"
    assert any(m.startswith("aucun tarif en vigueur") for m in rows[untariffed]["missing"])
    site = next(s for s in report["sites"] if s["site_id"] == str(w.t.sites["S1"]))
    assert site["revenue"] is None and site["margin"] is None and site["revenue_status"] == "INSUFFICIENT"

    # Accès : données commerciales réservées à DIRECTION, FINANCE, AUDITOR.
    assert client.get(f"{API}/finance/revenue", headers=api.user(w.t, "AUDITOR").headers).status_code == 200
    for account in (w.ops, w.dispatcher, w.hr):
        assert client.get(f"{API}/finance/revenue", headers=account.headers).status_code == 403
    other_site = api.user(w.t, "FINANCE", "SITE", "S2")
    assert all(c["contract_id"] not in rows for c in _report(client, other_site.headers)["contracts"])
    assert (
        client.get(
            f"{API}/finance/revenue", headers=other_site.headers, params={"site_id": str(w.t.sites["S1"])}
        ).status_code
        == 404
    )
    stranger = api.tenant(sites=("S1",))
    assert _report(client, api.user(stranger, "FINANCE").headers)["contracts"] == []
    too_long = client.get(
        f"{API}/finance/revenue",
        headers=api.user(w.t, "FINANCE").headers,
        params={"from": "2025-01-01T00:00:00Z", "to": "2026-06-01T00:00:00Z"},
    )
    assert too_long.status_code == 422


def test_hour_or_km_revenue_from_meter_readings_around_the_mission(
    client: TestClient,
    w: World,  # noqa: F811
    api: Api,
) -> None:
    """Décision du 18 novembre 2026 : relevé après la fin − relevé avant le départ, fenêtres de 2 h."""
    started = datetime.now(UTC)
    mid = _trip(client, w, None)  # trajet de référence : engin et catégorie
    mission = client.get(f"{API}/missions/{mid}", headers=w.ops.headers).json()
    vehicle = client.get(f"{API}/vehicles/{mission['vehicle_id']}", headers=w.ops.headers).json()
    category = next(
        c
        for c in client.get(f"{API}/vehicle-categories", headers=w.t.admin.headers).json()
        if c["vehicle_category_id"] == vehicle["vehicle_category_id"]
    )
    basis, kind, delta = (
        ("KM", "ODOMETER_KM", "12.5") if category["has_odometer"] else ("HOUR", "HOUR_METER", "0.4")
    )
    contract = _billable(client, w, api, {"basis": basis, "unit_price": "10000.0000"})
    measured = _trip(client, w, contract)
    unmeasured = _trip(client, w, contract)
    target = client.get(f"{API}/missions/{measured}", headers=w.ops.headers).json()["vehicle_id"]
    for value, at in (
        ("1000.0", started - timedelta(minutes=30)),
        (str(1000 + float(delta)), datetime.now(UTC)),
    ):
        reading = client.post(
            f"{API}/vehicles/{target}/meter-readings",
            headers=w.ops.headers,
            json={"meter_kind": kind, "value": value, "read_at": at.isoformat()},
        )
        assert reading.status_code == 201, reading.text
    assert unmeasured  # mission du même contrat sans relevé : signalée, jamais estimée

    report = _report(client, api.user(w.t, "FINANCE").headers)
    row = next(c for c in report["contracts"] if c["contract_id"] == contract)
    expected = (Decimal(delta) * Decimal("10000")).quantize(Decimal("0.01"))
    assert row["amount"] == str(expected) and row["currency"] == "GNF"
    assert row[basis.lower() if basis == "KM" else "hours"] == delta
    assert row["status"] == "PARTIAL" and row["missions_completed"] == 2
    assert any("manquant au départ" in m for m in row["missing"])
