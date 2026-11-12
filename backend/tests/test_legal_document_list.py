"""Consultation des justificatifs déposés (GET documents) — états PENDING/VERIFIED exposés à l'UI."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from tests.conftest import API, Api


def test_document_list_scopes_and_empty(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    other = api.tenant(sites=("OTHER",))
    owner = api.user(tenant, "OPS_MANAGER", "SITE", "MINE")
    auditor = api.user(tenant, "AUDITOR", "TENANT")
    driver = api.user(tenant, "DRIVER", "SITE", "MINE")
    outsider = api.user(other, "TENANT_ADMIN", "TENANT")
    created = client.post(
        f"{API}/legal-contracts",
        headers=owner.headers,
        json={
            "site_id": str(tenant.sites["MINE"]),
            "reference": "LIST-HTTP-001",
            "title": "Contrat transport",
            "contract_type": "TRANSPORT",
            "counterparty_name": "Entreprise",
        },
    )
    assert created.status_code == 201, created.text
    path = f"{API}/legal-contracts/{created.json()['contract_id']}/documents"
    forbidden = client.get(path, headers=driver.headers)
    assert forbidden.status_code == 403
    hidden = client.get(path, headers=outsider.headers)
    assert hidden.status_code == 404
    missing = client.get(
        f"{API}/legal-contracts/00000000-0000-4000-8000-0000000000aa/documents",
        headers=owner.headers,
    )
    assert missing.status_code == 404
    listed = client.get(path, headers=owner.headers)
    assert listed.status_code == 200, listed.text
    assert listed.json() == []
    auditor_list = client.get(path, headers=auditor.headers)
    assert auditor_list.status_code == 200 and auditor_list.json() == []


def _insert_document(api: Api, tenant_id: str, contract_id: str, document_id: str) -> None:
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})
            conn.execute(
                text(
                    "INSERT INTO legal_contract_document "
                    "(document_id, tenant_id, contract_id, sha256, object_key, original_filename, "
                    "content_type, byte_size, status, uploaded_by) "
                    "VALUES (:d, :t, :c, :sha, :key, 'justificatif-e2e.pdf', 'application/pdf', 1024, "
                    "'PENDING', (SELECT user_account_id FROM user_account WHERE tenant_id = :t LIMIT 1))"
                ),
                {
                    "d": document_id,
                    "t": tenant_id,
                    "c": contract_id,
                    "sha": "a" * 64,
                    "key": f"legal/{tenant_id}/contracts/{contract_id}/{document_id}.pdf",
                },
            )
    finally:
        engine.dispose()


def _set_status(api: Api, tenant_id: str, document_id: str, status: str) -> None:
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})
            conn.execute(
                text(
                    "UPDATE legal_contract_document SET status = :s, "
                    "verified_at = CASE WHEN :s = 'VERIFIED' THEN now() ELSE NULL END, "
                    "stored_object_verified = :v, malware_scan_passed = :v "
                    "WHERE tenant_id = :t AND document_id = :d"
                ),
                {"s": status, "v": status == "VERIFIED", "t": tenant_id, "d": document_id},
            )
    finally:
        engine.dispose()


def test_document_list_exposes_pending_verified_rejected(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    owner = api.user(tenant, "OPS_MANAGER", "SITE", "MINE")
    created = client.post(
        f"{API}/legal-contracts",
        headers=owner.headers,
        json={
            "site_id": str(tenant.sites["MINE"]),
            "reference": "LIST-HTTP-002",
            "title": "Contrat fournisseur",
            "contract_type": "SUPPLIER",
            "counterparty_name": "Fournisseur",
        },
    )
    assert created.status_code == 201, created.text
    contract_id = created.json()["contract_id"]
    document_id = "00000000-0000-4000-8000-0000000000bb"
    _insert_document(api, str(tenant.tenant_id), contract_id, document_id)
    path = f"{API}/legal-contracts/{contract_id}/documents"

    pending = client.get(path, headers=owner.headers)
    assert pending.status_code == 200, pending.text
    assert [d["status"] for d in pending.json()] == ["PENDING"]
    first = pending.json()[0]
    assert first["document_id"] == document_id
    assert first["original_filename"] == "justificatif-e2e.pdf"
    assert first["sha256"] == "a" * 64
    assert first["byte_size"] == 1024

    for status in ("VERIFIED", "PENDING"):
        _set_status(api, str(tenant.tenant_id), document_id, status)
        listed = client.get(path, headers=owner.headers)
        assert [d["status"] for d in listed.json()] == [status]
