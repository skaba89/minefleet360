"""Submitting a contract requires an actual document and a scoped actor."""

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def test_submit_contract_requires_document_and_role(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    manager = api.user(tenant, "OPS_MANAGER", "SITE", "MINE")
    driver = api.user(tenant, "DRIVER", "SITE", "MINE")
    base = {
        "site_id": str(tenant.sites["MINE"]),
        "reference": "SUBMISSION-001",
        "title": "Transport",
        "contract_type": "TRANSPORT",
        "counterparty_name": "Transporteur",
    }
    unsigned = client.post(f"{API}/legal-contracts", headers=manager.headers, json=base)
    assert unsigned.status_code == 201, unsigned.text
    contract_id = unsigned.json()["contract_id"]
    forbidden = client.post(f"{API}/legal-contracts/{contract_id}/submit", headers=driver.headers)
    assert forbidden.status_code == 403
    missing = client.post(f"{API}/legal-contracts/{contract_id}/submit", headers=manager.headers)
    assert missing.status_code == 409

    document = client.post(
        f"{API}/legal-contracts",
        headers=manager.headers,
        json={**base, "reference": "SUBMISSION-002", "document_sha256": "a" * 64},
    )
    assert document.status_code == 201, document.text
    ready_id = document.json()["contract_id"]
    submitted = client.post(f"{API}/legal-contracts/{ready_id}/submit", headers=manager.headers)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "PENDING_REVIEW"
    repeated = client.post(f"{API}/legal-contracts/{ready_id}/submit", headers=manager.headers)
    assert repeated.status_code == 409
