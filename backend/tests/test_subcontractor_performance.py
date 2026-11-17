"""Performance mesurée et SLA de disponibilité par sous-traitant (lot 1, tranche 3)."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_assignment import World, w  # noqa: F401  (fixture w)
from tests.test_maintenance_reliability import _backdate_at, _closed_order

T2 = datetime(2026, 5, 1, tzinfo=UTC)  # période distincte des autres tests de fiabilité


def _t2(hours: float) -> datetime:
    return T2 + timedelta(hours=hours)


def _partner(client: TestClient, w: World, target: str | None) -> str:  # noqa: F811
    body: dict[str, object] = {
        "code": f"ST-{uuid.uuid4().hex[:6].upper()}",
        "legal_name": "Sous-traitant fictif",
    }
    if target is not None:
        body["availability_target_percent"] = target
    resp = client.post(f"{API}/subcontractors", headers=w.t.admin.headers, json=body)
    assert resp.status_code == 201, resp.text
    assert resp.json()["availability_target_percent"] == target
    return str(resp.json()["subcontractor_id"])


def _vehicle(client: TestClient, w: World, partner: str | None) -> str:  # noqa: F811
    category = client.get(f"{API}/vehicle-categories", headers=w.t.admin.headers).json()[0][
        "vehicle_category_id"
    ]
    body: dict[str, object] = {
        "site_id": str(w.t.sites["S1"]),
        "vehicle_category_id": category,
        "fleet_number": f"PS-{uuid.uuid4().hex[:6]}",
        "ownership_type": "SUBCONTRACTED",
    }
    if partner is not None:
        body["subcontractor_id"] = partner
    resp = client.post(f"{API}/vehicles", headers=w.t.admin.headers, json=body)
    assert resp.status_code == 201, resp.text
    return str(resp.json()["vehicle_id"])


def test_performance_aggregates_linked_vehicles_against_the_sla(
    client: TestClient,
    w: World,  # noqa: F811
    api: Api,
) -> None:
    chief = api.user(w.t, "WORKSHOP_CHIEF")
    mechanic = api.user(w.t, "MECHANIC", "SITE", "S1")
    met, missed, idle = _partner(client, w, "90.00"), _partner(client, w, "95.00"), _partner(client, w, None)
    a1, b1 = _vehicle(client, w, met), _vehicle(client, w, missed)
    _vehicle(client, w, met)  # second engin de A, sans panne : 100 h de service disponibles
    unlinked = _vehicle(client, w, None)
    for vehicle, reported, closed in ((a1, 10, 30), (b1, 40, 50), (unlinked, 0, 90)):
        order = _closed_order(client, w, vehicle, chief, mechanic, immobilize=True)
        _backdate_at(w, order, reported=_t2(reported), closed=_t2(closed))
    params = {"from": T2.isoformat(), "to": _t2(100).isoformat()}

    finance = api.user(w.t, "FINANCE")
    resp = client.get(f"{API}/subcontractors/performance", headers=finance.headers, params=params)
    assert resp.status_code == 200, resp.text
    rows = {r["subcontractor_id"]: r for r in resp.json()["subcontractors"]}
    a = rows[met]
    assert (a["vehicles"], a["service_hours"], a["downtime_hours"]) == (2, "200.00", "20.00")
    assert a["availability_percent"] == "90.00" and a["sla_met"] is True  # objectif atteint (≥ 90 %)
    assert (a["failures"], a["mtbf_hours"], a["mttr_hours"]) == (1, "180.00", "20.00")
    b = rows[missed]
    assert (b["vehicles"], b["availability_percent"], b["sla_met"]) == (
        1,
        "90.00",
        False,
    )  # objectif 95 % manqué
    c = rows[idle]
    assert (c["vehicles"], c["availability_percent"], c["sla_met"]) == (0, None, None)
    # L'engin non rattaché (90 h d'immobilisation) n'entre dans aucun agrégat.
    assert sum(r["vehicles"] for r in rows.values() if r["subcontractor_id"] in (met, missed, idle)) == 3


def test_performance_permissions_and_scope(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    partner = _partner(client, w, "80.00")
    _vehicle(client, w, partner)
    params = {"from": T2.isoformat(), "to": _t2(100).isoformat()}
    for role, scope, site in (
        ("WORKSHOP_CHIEF", "TENANT", None),
        ("HR", "TENANT", None),
        ("DISPATCHER", "SITE", "S1"),
    ):
        viewer = api.user(w.t, role, scope, site) if site else api.user(w.t, role)
        refused = client.get(f"{API}/subcontractors/performance", headers=viewer.headers, params=params)
        assert refused.status_code == 403, role
    # OPS_MANAGER d'un autre site : sous-traitant listé, aucun engin hors de sa portée agrégé.
    s2_ops = api.user(w.t, "OPS_MANAGER", "SITE", "S2")
    seen = client.get(f"{API}/subcontractors/performance", headers=s2_ops.headers, params=params).json()
    row = next(r for r in seen["subcontractors"] if r["subcontractor_id"] == partner)
    assert (row["vehicles"], row["availability_percent"]) == (0, None)
    other = api.tenant()
    foreign = client.get(f"{API}/subcontractors/performance", headers=other.admin.headers, params=params)
    assert foreign.status_code == 403  # TENANT_ADMIN ne lit pas la performance
