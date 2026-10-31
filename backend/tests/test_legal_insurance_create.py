"""Policy creation permissions and site/contract isolation."""

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def test_insurance_policy_create_guards(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    manager = api.user(tenant, "OPS_MANAGER", "SITE", "MINE")
    driver = api.user(tenant, "DRIVER", "SITE", "MINE")
    foreign = api.tenant(sites=("OTHER",))
    payload = {
        "site_id": str(tenant.sites["MINE"]),
        "policy_number": "POL-TEST-001",
        "insurer_name": "Assureur Test",
        "coverage_type": "FLEET",
        "coverage_start": "2026-01-01",
        "coverage_end": "2026-12-31",
    }
    denied = client.post(f"{API}/insurance-policies", headers=driver.headers, json=payload)
    assert denied.status_code == 403
    hidden = client.post(
        f"{API}/insurance-policies",
        headers=manager.headers,
        json={**payload, "site_id": str(foreign.sites["OTHER"])},
    )
    assert hidden.status_code == 404
    invalid_contract = client.post(
        f"{API}/insurance-policies",
        headers=manager.headers,
        json={**payload, "contract_id": str(foreign.sites["OTHER"])},
    )
    assert invalid_contract.status_code == 404
    invalid_dates = client.post(
        f"{API}/insurance-policies",
        headers=manager.headers,
        json={**payload, "coverage_end": "2025-01-01"},
    )
    assert invalid_dates.status_code == 422
    created = client.post(f"{API}/insurance-policies", headers=manager.headers, json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["policy_number"] == "POL-TEST-001"
    repeated = client.post(f"{API}/insurance-policies", headers=manager.headers, json=payload)
    assert repeated.status_code == 409
    listed = client.get(f"{API}/insurance-policies", headers=manager.headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
