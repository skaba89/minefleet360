"""Contract decisions require another authorized user and a submitted contract."""

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def test_contract_review_separation_and_replay(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    creator = api.user(tenant, "TENANT_ADMIN", "TENANT")
    reviewer = api.user(tenant, "DIRECTION", "TENANT")
    operator = api.user(tenant, "OPS_MANAGER", "SITE", "MINE")
    body = {
        "site_id": str(tenant.sites["MINE"]),
        "reference": "REVIEW-DECISION-001",
        "title": "Transport",
        "contract_type": "TRANSPORT",
        "counterparty_name": "Partner",
        "document_sha256": "a" * 64,
    }
    draft = client.post(f"{API}/legal-contracts", headers=creator.headers, json=body)
    assert draft.status_code == 201, draft.text
    contract_id = draft.json()["contract_id"]
    endpoint = f"{API}/legal-contracts/{contract_id}/decision"
    premature = client.post(endpoint, headers=reviewer.headers, json={"action": "APPROVE", "note": "OK"})
    assert premature.status_code == 409
    submitted = client.post(f"{API}/legal-contracts/{contract_id}/submit", headers=creator.headers)
    # Until private storage and antivirus verification exist, no review can start.
    assert submitted.status_code == 409, submitted.text

    forbidden = client.post(endpoint, headers=operator.headers, json={"action": "APPROVE", "note": "OK"})
    assert forbidden.status_code == 403
    self_review = client.post(endpoint, headers=creator.headers, json={"action": "APPROVE", "note": "OK"})
    assert self_review.status_code == 409
    empty = client.post(endpoint, headers=reviewer.headers, json={"action": "APPROVE", "note": " "})
    assert empty.status_code == 422
    blocked = client.post(endpoint, headers=reviewer.headers, json={"action": "APPROVE", "note": "Validé"})
    assert blocked.status_code == 409
