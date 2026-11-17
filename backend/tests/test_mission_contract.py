"""Rattachement d'une mission à un contrat de transport approuvé (contrôle de gestion, tranche 2b)."""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_assignment import World, w  # noqa: F401  (fixture w)
from tests.test_contract_tariffs import _approve, _contract
from tests.test_dispatch import _assignment, _now, _refs


def _create(client: TestClient, w: World, contract_id: str | None, headers=None, **extra):  # type: ignore[no-untyped-def]  # noqa: F811
    refs = _refs(client, w)
    assignment = _assignment(client, w)
    body = {
        "vehicle_assignment_id": assignment["vehicle_assignment_id"],
        "origin_location_id": refs["origin"],
        "destination_location_id": refs["destination"],
        "material_id": refs["material"],
        "planned_start": _now().isoformat(),
        "contract_id": contract_id,
        **extra,
    }
    return client.post(f"{API}/missions", headers=headers or w.ops.headers, json=body), body


def test_mission_linked_to_an_approved_transport_contract(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    contract = _contract(client, w.t, site="S1")
    _approve(w.t, contract, api.user(w.t, "DIRECTION"))
    billable = client.get(f"{API}/dispatch/billable-contracts", headers=w.dispatcher.headers)
    assert billable.status_code == 200, billable.text
    assert contract in {c["contract_id"] for c in billable.json()}

    created, body = _create(
        client, w, contract, headers=w.dispatcher.headers, client_request_id=str(uuid.uuid4())
    )
    assert created.status_code == 201, created.text
    mission = created.json()
    assert mission["contract_id"] == contract and mission["contract_reference"].startswith("CT-")
    detail = client.get(f"{API}/missions/{mission['mission_id']}", headers=w.ops.headers).json()
    assert detail["contract_id"] == contract
    # Renvoi hors ligne : même contrat → même mission ; contrat différent → conflit.
    replay = client.post(f"{API}/missions", headers=w.dispatcher.headers, json=body)
    assert replay.status_code == 201 and replay.json()["mission_id"] == mission["mission_id"]
    changed = client.post(f"{API}/missions", headers=w.dispatcher.headers, json={**body, "contract_id": None})
    assert changed.status_code == 409
    audit = client.get(
        f"{API}/audit-events", headers=w.t.admin.headers, params={"action": "mission.create", "page_size": 5}
    ).json()["items"]
    assert any((a.get("after_data") or {}).get("contract_id") == contract for a in audit)
    # Sans contrat : inchangé (champ facultatif).
    plain, _ = _create(client, w, None)
    assert plain.status_code == 201 and plain.json()["contract_id"] is None


def test_mission_contract_must_be_billable_same_site_same_tenant(
    client: TestClient,
    w: World,  # noqa: F811
    api: Api,
) -> None:
    direction = api.user(w.t, "DIRECTION")
    draft = _contract(client, w.t, site="S1")
    refused, _ = _create(client, w, draft)
    assert (refused.status_code, refused.json()["details"][0]["type"]) == (422, "not_billable")
    supplier = _contract(client, w.t, site="S1", contract_type="SUPPLIER")
    _approve(w.t, supplier, direction)
    wrong_type, _ = _create(client, w, supplier)
    assert (wrong_type.status_code, wrong_type.json()["details"][0]["type"]) == (422, "not_billable")
    other_site = _contract(client, w.t, site="S2")
    _approve(w.t, other_site, direction)
    mismatch, _ = _create(client, w, other_site)
    assert (mismatch.status_code, mismatch.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    other = api.tenant(sites=("S1",))
    foreign = _contract(client, other, site="S1")
    _approve(other, foreign, api.user(other, "DIRECTION"))
    stolen, _ = _create(client, w, foreign)
    assert (stolen.status_code, stolen.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    # Le répartiteur du site S1 ne voit ni le contrat de S2 ni celui d'un autre tenant.
    visible = {
        c["contract_id"]
        for c in client.get(f"{API}/dispatch/billable-contracts", headers=w.dispatcher.headers).json()
    }
    assert other_site not in visible and foreign not in visible and draft not in visible
    # Sans droit de création de mission : pas de liste.
    assert client.get(f"{API}/dispatch/billable-contracts", headers=w.hr.headers).status_code == 403
