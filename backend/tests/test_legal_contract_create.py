"""Draft creation is scoped and never signs contracts."""

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def test_create_contract_draft_guards(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    manager = api.user(tenant, "OPS_MANAGER", "SITE", "MINE")
    driver = api.user(tenant, "DRIVER", "SITE", "MINE")
    foreign = api.tenant(sites=("OTHER",))
    body = {
        "site_id": str(tenant.sites["MINE"]),
        "reference": "LEGAL-001",
        "title": "Contrat de transport",
        "contract_type": "TRANSPORT",
        "counterparty_name": "Transporteur test",
    }
    denied = client.post(f"{API}/legal-contracts", headers=driver.headers, json=body)
    assert denied.status_code == 403
    hidden = client.post(
        f"{API}/legal-contracts",
        headers=manager.headers,
        json={**body, "site_id": str(foreign.sites["OTHER"])},
    )
    assert hidden.status_code == 404
    created = client.post(f"{API}/legal-contracts", headers=manager.headers, json=body)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "DRAFT"
    assert created.json()["reference"] == "LEGAL-001"
    listed = client.get(f"{API}/legal-contracts", headers=manager.headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    repeated = client.post(f"{API}/legal-contracts", headers=manager.headers, json=body)
    assert repeated.status_code == 409

    injected = client.post(
        f"{API}/legal-contracts",
        headers=manager.headers,
        json={**body, "tenant_id": str(foreign.tenant_id)},
    )
    assert injected.status_code == 422
