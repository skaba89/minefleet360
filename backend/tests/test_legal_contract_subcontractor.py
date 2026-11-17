"""Rattachement d'un contrat de sous-traitance au référentiel (lot 1, tranche 2b), à la création."""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import API, Api, TenantFixture


def _subcontractor(client: TestClient, t: TenantFixture, *, ended: bool = False) -> str:
    created = client.post(
        f"{API}/subcontractors",
        headers=t.admin.headers,
        json={"code": f"ST-{uuid.uuid4().hex[:6].upper()}", "legal_name": "Transports Fictifs SARL"},
    )
    assert created.status_code == 201, created.text
    item = created.json()
    if ended:
        resp = client.patch(
            f"{API}/subcontractors/{item['subcontractor_id']}",
            headers={**t.admin.headers, "If-Match": f'"{item["row_version"]}"'},
            json={"status": "ENDED", "status_reason": "Fin de la relation"},
        )
        assert resp.status_code == 200, resp.text
    return str(item["subcontractor_id"])


def _body(t: TenantFixture, **extra: object) -> dict[str, object]:
    return {
        "site_id": str(t.sites["MINE"]),
        "reference": f"ST-{uuid.uuid4().hex[:8]}",
        "title": "Contrat de sous-traitance transport",
        "contract_type": "SUBCONTRACTOR",
        "counterparty_name": "Transports Fictifs SARL",
        **extra,
    }


def test_contract_draft_links_to_an_active_subcontractor(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("MINE",))
    manager = api.user(t, "OPS_MANAGER", "SITE", "MINE")  # lit le référentiel en SITE (#466)
    partner = _subcontractor(client, t)
    assert client.get(f"{API}/subcontractors", headers=manager.headers).status_code == 200

    created = client.post(
        f"{API}/legal-contracts", headers=manager.headers, json=_body(t, subcontractor_id=partner)
    )
    assert created.status_code == 201, created.text
    assert created.json()["subcontractor_id"] == partner and created.json()["status"] == "DRAFT"
    listed = client.get(f"{API}/legal-contracts", headers=manager.headers).json()["items"]
    assert [c["subcontractor_id"] for c in listed if c["contract_id"] == created.json()["contract_id"]] == [
        partner
    ]

    # Contrat de sous-traitance sans rattachement : toujours permis (pas de reprise automatique).
    plain = client.post(f"{API}/legal-contracts", headers=manager.headers, json=_body(t))
    assert plain.status_code == 201 and plain.json()["subcontractor_id"] is None


def test_contract_subcontractor_link_is_validated(client: TestClient, api: Api) -> None:
    t, other = api.tenant(sites=("MINE",)), api.tenant(sites=("MINE",))
    partner = _subcontractor(client, t)
    wrong_type = client.post(
        f"{API}/legal-contracts",
        headers=t.admin.headers,
        json=_body(t, contract_type="TRANSPORT", subcontractor_id=partner),
    )
    assert wrong_type.status_code == 422
    for missing in (str(uuid.uuid4()), _subcontractor(client, other)):  # inconnu ou d'un autre tenant
        refused = client.post(
            f"{API}/legal-contracts", headers=t.admin.headers, json=_body(t, subcontractor_id=missing)
        )
        assert (refused.status_code, refused.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    ended = client.post(
        f"{API}/legal-contracts",
        headers=t.admin.headers,
        json=_body(t, subcontractor_id=_subcontractor(client, t, ended=True)),
    )
    assert ended.status_code == 422 and ended.json()["details"][0]["type"] == "not_active"
