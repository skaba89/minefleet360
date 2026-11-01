"""Real HTTP upload is scoped and fails closed without configured scanners/storage."""

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def test_contract_document_upload_fail_closed(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    other = api.tenant(sites=("OTHER",))
    owner = api.user(tenant, "OPS_MANAGER", "SITE", "MINE")
    outsider = api.user(other, "TENANT_ADMIN", "TENANT")
    driver = api.user(tenant, "DRIVER", "SITE", "MINE")
    created = client.post(
        f"{API}/legal-contracts",
        headers=owner.headers,
        json={
            "site_id": str(tenant.sites["MINE"]),
            "reference": "UPLOAD-HTTP-001",
            "title": "Contrat transport",
            "contract_type": "TRANSPORT",
            "counterparty_name": "Entreprise",
        },
    )
    assert created.status_code == 201, created.text
    path = f"{API}/legal-contracts/{created.json()['contract_id']}/documents"
    headers = {"Content-Type": "application/pdf", "X-Filename": "contract.pdf"}
    pdf = b"%PDF-1.7\n%%EOF\n"
    forbidden = client.post(path, headers={**driver.headers, **headers}, content=pdf)
    assert forbidden.status_code == 403
    hidden = client.post(path, headers={**outsider.headers, **headers}, content=pdf)
    assert hidden.status_code == 404
    unavailable = client.post(path, headers={**owner.headers, **headers}, content=pdf)
    assert unavailable.status_code == 503
    wrong_type = client.post(
        path,
        headers={**owner.headers, "Content-Type": "text/plain", "X-Filename": "contract.pdf"},
        content=pdf,
    )
    assert wrong_type.status_code == 422
