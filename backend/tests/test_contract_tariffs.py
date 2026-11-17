"""Tarifs des contrats de transport (contrôle de gestion, tranche 2a)."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from tests.conftest import API, Account, Api, TenantFixture


def _contract(
    client: TestClient, t: TenantFixture, *, site: str = "MINE", contract_type: str = "TRANSPORT"
) -> str:
    resp = client.post(
        f"{API}/legal-contracts",
        headers=t.admin.headers,
        json={
            "site_id": str(t.sites[site]),
            "reference": f"CT-{uuid.uuid4().hex[:8]}",
            "title": "Contrat de transport fictif",
            "contract_type": contract_type,
            "counterparty_name": "Client minier fictif",
            "document_sha256": "a" * 64,
        },
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["contract_id"])


def _approve(t: TenantFixture, contract_id: str, reviewer: Account) -> None:
    """Le circuit quatre-yeux exige stockage privé et antivirus, absents de la CI : état final posé en base,
    dans le respect de ck_legal_contract_review_consistency (relecteur distinct du créateur)."""
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(t.tenant_id)})
            conn.execute(
                text(
                    "UPDATE legal_contract SET status = 'APPROVED', submitted_at = now(), "
                    "reviewed_by = :r, reviewed_at = now(), review_note = 'Approbation fictive' "
                    "WHERE contract_id = :c"
                ),
                {"r": str(reviewer.user_id), "c": contract_id},
            )
    finally:
        engine.dispose()


def _tariff(client: TestClient, headers: dict[str, str], contract_id: str, **extra: object):  # type: ignore[no-untyped-def]
    body = {
        "contract_id": contract_id,
        "basis": "TONNE",
        "unit_price": "25000.0000",
        "currency": "GNF",
        "valid_from": "2026-01-01",
        **extra,
    }
    return client.post(f"{API}/contract-tariffs", headers=headers, json=body)


def test_tariff_versions_on_an_approved_transport_contract(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("MINE",))
    finance = api.user(t, "FINANCE")
    contract = _contract(client, t)
    _approve(t, contract, api.user(t, "DIRECTION"))

    first = _tariff(client, finance.headers, contract)
    assert first.status_code == 201, first.text
    assert (first.json()["basis"], first.json()["unit_price"]) == ("TONNE", "25000.0000")
    revised = _tariff(client, finance.headers, contract, unit_price="27500.0000", valid_from="2026-06-01")
    assert revised.status_code == 201, revised.text
    future_day = (datetime.now(UTC) + timedelta(days=30)).date().isoformat()
    future = _tariff(client, finance.headers, contract, unit_price="30000.0000", valid_from=future_day)
    assert future.status_code == 201, future.text
    same_day = _tariff(client, finance.headers, contract, unit_price="1.0000", valid_from="2026-06-01")
    assert same_day.status_code == 409  # une seule version par date d'effet

    listed = client.get(f"{API}/contract-tariffs", headers=finance.headers, params={"contract_id": contract})
    assert listed.status_code == 200, listed.text
    versions = listed.json()
    assert [v["valid_from"] for v in versions] == [future_day, "2026-06-01", "2026-01-01"]
    # En vigueur aujourd'hui : la version du 1er juin, pas la version future.
    assert [v["current"] for v in versions] == [False, True, False]

    audit = client.get(
        f"{API}/audit-events",
        headers=t.admin.headers,
        params={"action": "finance.tariff.create", "page_size": 20},
    ).json()["items"]
    assert len(audit) == 3


def test_tariff_rules_permissions_and_isolation(client: TestClient, api: Api) -> None:
    t, other = api.tenant(sites=("MINE", "PORT")), api.tenant(sites=("MINE",))
    direction = api.user(t, "DIRECTION")
    finance = api.user(t, "FINANCE")
    draft = _contract(client, t)  # jamais approuvé
    refused = _tariff(client, finance.headers, draft)
    assert refused.status_code == 422 and refused.json()["details"][0]["type"] == "not_approved"
    supplier = _contract(client, t, contract_type="SUPPLIER")
    _approve(t, supplier, direction)
    wrong_type = _tariff(client, finance.headers, supplier)
    assert wrong_type.status_code == 422 and wrong_type.json()["details"][0]["type"] == "not_transport"
    foreign = _contract(client, other)
    _approve(other, foreign, api.user(other, "DIRECTION"))
    stolen = _tariff(client, finance.headers, foreign)
    assert (stolen.status_code, stolen.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    unknown = _tariff(client, finance.headers, str(uuid.uuid4()))
    assert (unknown.status_code, unknown.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    # Finance d'un seul site : contrat d'un autre site invisible, en écriture comme en lecture.
    port = _contract(client, t, site="PORT")
    _approve(t, port, direction)
    assert _tariff(client, finance.headers, port).status_code == 201
    site_finance = api.user(t, "FINANCE", "SITE", "MINE")
    hidden = _tariff(client, site_finance.headers, port, valid_from="2026-02-01")
    assert (hidden.status_code, hidden.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    listed = client.get(f"{API}/contract-tariffs", headers=site_finance.headers).json()
    assert all(v["contract_id"] != port for v in listed)
    assert (
        client.get(
            f"{API}/contract-tariffs", headers=site_finance.headers, params={"contract_id": port}
        ).status_code
        == 404
    )
    # Liste des contrats facturables : approuvés, TRANSPORT, sites couverts, jamais d'un autre tenant.
    billable = {
        c["contract_id"]
        for c in client.get(f"{API}/contract-tariffs/contracts", headers=finance.headers).json()
    }
    assert port in billable and draft not in billable and supplier not in billable and foreign not in billable
    site_billable = client.get(f"{API}/contract-tariffs/contracts", headers=site_finance.headers).json()
    assert all(c["contract_id"] != port for c in site_billable)
    # Rôles : OPS_MANAGER lit sans saisir ; WORKSHOP_CHIEF et DISPATCHER ne lisent pas.
    ops = api.user(t, "OPS_MANAGER")
    assert client.get(f"{API}/contract-tariffs", headers=ops.headers).status_code == 200
    assert _tariff(client, ops.headers, port, valid_from="2026-03-01").status_code == 403
    for role, scope, site in (("WORKSHOP_CHIEF", "TENANT", None), ("DISPATCHER", "SITE", "MINE")):
        viewer = api.user(t, role, scope, site) if site else api.user(t, role)
        assert client.get(f"{API}/contract-tariffs", headers=viewer.headers).status_code == 403, role
    # Validations : mode, prix, devise.
    assert _tariff(client, finance.headers, port, basis="LITRE", valid_from="2026-04-01").status_code == 422
    assert _tariff(client, finance.headers, port, unit_price="0", valid_from="2026-04-01").status_code == 422
    assert _tariff(client, finance.headers, port, currency="gnf", valid_from="2026-04-01").status_code == 422
