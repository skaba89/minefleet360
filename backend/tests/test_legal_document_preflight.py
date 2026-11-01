"""Contract document preflight checks RBAC, tenant and draft status."""

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def test_document_preflight_is_scoped_and_does_not_upload(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    other = api.tenant(sites=("OTHER",))
    manager = api.user(tenant, "OPS_MANAGER", "SITE", "MINE")
    driver = api.user(tenant, "DRIVER", "SITE", "MINE")
    outsider = api.user(other, "TENANT_ADMIN", "TENANT")
    response = client.post(
        f"{API}/legal-contracts",
        headers=manager.headers,
        json={
            "site_id": str(tenant.sites["MINE"]),
            "reference": "UPLOAD-PREFLIGHT-001",
            "title": "Transport",
            "contract_type": "TRANSPORT",
            "counterparty_name": "Transporteur",
        },
    )
    assert response.status_code == 201, response.text
    endpoint = f"{API}/legal-contracts/{response.json()['contract_id']}/documents/preflight"
    allowed = client.post(endpoint, headers=manager.headers)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json() == {"allowed": True}
    assert client.post(endpoint, headers=driver.headers).status_code == 403
    assert client.post(endpoint, headers=outsider.headers).status_code == 404
