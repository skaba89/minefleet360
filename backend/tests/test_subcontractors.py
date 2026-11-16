"""Référentiel des sous-traitants — lot 1 (option B, docs/MODELE_SECURITE_SOUS_TRAITANTS.md).

Données du donneur d'ordre : gérées par TENANT_ADMIN / OPS_MANAGER, lues par les rôles internes listés dans la
matrice ; aucun compte externe. Isolation tenant (RLS), verrouillage optimiste, audit de chaque écriture.
"""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import API, Api, TenantFixture


def _create(client: TestClient, t: TenantFixture, **extra: object):  # type: ignore[no-untyped-def]
    body: dict[str, object] = {
        "code": f"ST-{uuid.uuid4().hex[:6].upper()}",
        "legal_name": "Transports Fictifs SARL",
        "registration_number": "RCCM-FICTIF-0001",
        "tax_id": "NIF-FICTIF-0001",
        **extra,
    }
    return client.post(f"{API}/subcontractors", headers=t.admin.headers, json=body)


def _patch(client: TestClient, headers: dict[str, str], item: dict, **body: object):  # type: ignore[no-untyped-def,type-arg]
    return client.patch(
        f"{API}/subcontractors/{item['subcontractor_id']}",
        headers={**headers, "If-Match": f'"{item["row_version"]}"'},
        json=body,
    )


def test_subcontractor_lifecycle_and_audit(client: TestClient, api: Api) -> None:
    t = api.tenant()
    created = _create(client, t)
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["status"] == "ACTIVE" and item["status_reason"] is None and item["country_code"] == "GN"
    assert created.headers["ETag"] == f'"{item["row_version"]}"'

    ops = api.user(t, "OPS_MANAGER")
    renamed = _patch(
        client, ops.headers, item, legal_name="  Transports Fictifs SA  ", notes="Contrat cadre 2026"
    )
    assert renamed.status_code == 200, renamed.text
    item = renamed.json()
    assert item["legal_name"] == "Transports Fictifs SA" and item["notes"] == "Contrat cadre 2026"

    suspended = _patch(client, ops.headers, item, status="SUSPENDED", status_reason="Assurance expirée")
    assert suspended.status_code == 200, suspended.text
    item = suspended.json()
    assert (item["status"], item["status_reason"]) == ("SUSPENDED", "Assurance expirée")
    assert [
        s["code"]
        for s in client.get(f"{API}/subcontractors", headers=ops.headers, params={"status": "ACTIVE"}).json()
    ] == []

    reactivated = _patch(client, ops.headers, item, status="ACTIVE")
    assert reactivated.status_code == 200, reactivated.text
    item = reactivated.json()
    assert (item["status"], item["status_reason"]) == ("ACTIVE", None)  # le motif précédent est effacé

    ended = _patch(client, t.admin.headers, item, status="ENDED", status_reason="Fin du contrat de transport")
    assert ended.status_code == 200 and ended.json()["status"] == "ENDED"

    actions = [
        e["action"]
        for e in client.get(
            f"{API}/audit-events",
            headers=t.admin.headers,
            params={"entity_type": "subcontractor", "page_size": 50},
        ).json()["items"]
        if e["entity_id"] == item["subcontractor_id"]
    ]
    assert sorted(actions) == sorted(
        [
            "subcontractor.create",
            "subcontractor.update",
            "subcontractor.status_change",
            "subcontractor.status_change",
            "subcontractor.status_change",
        ]
    )


def test_subcontractor_validation(client: TestClient, api: Api) -> None:
    t = api.tenant()
    item = _create(client, t).json()
    duplicate = _create(client, t, code=item["code"])
    assert (duplicate.status_code, duplicate.json()["code"]) == (409, "DUPLICATE_SUBCONTRACTOR_CODE")
    assert _create(client, t, code="code invalide!").status_code == 422
    assert _create(client, t, legal_name="   ").status_code == 422
    assert _create(client, t, country_code="gn").status_code == 422
    # Champ inconnu ou tenant_id dans le corps : refusés (schéma strict).
    assert _create(client, t, tenant_id=str(uuid.uuid4())).status_code == 422
    assert _create(client, t, contact_email="personne@example.com").status_code == 422
    # Suspension ou fin sans motif, motif sur une réactivation, motif sans statut : refusés.
    assert _patch(client, t.admin.headers, item, status="SUSPENDED").status_code == 422
    assert (
        _patch(client, t.admin.headers, item, status="ACTIVE", status_reason="Sans objet").status_code == 422
    )
    assert _patch(client, t.admin.headers, item, status_reason="Motif orphelin").status_code == 422
    # Verrouillage optimiste : version périmée → 409, sans If-Match → IF_MATCH_REQUIRED.
    fresh = _patch(client, t.admin.headers, item, notes="Première modification").json()
    stale = _patch(client, t.admin.headers, item, notes="Écrase la précédente")
    assert stale.status_code == 409
    missing = client.patch(
        f"{API}/subcontractors/{fresh['subcontractor_id']}", headers=t.admin.headers, json={"notes": "x"}
    )
    assert (missing.status_code, missing.json()["code"]) == (422, "IF_MATCH_REQUIRED")


def test_subcontractor_isolation_and_permissions(client: TestClient, api: Api) -> None:
    t, other = api.tenant(), api.tenant()
    item = _create(client, t).json()
    # Autre tenant : invisible en liste, indiscernable d'un identifiant inexistant en écriture.
    assert item["subcontractor_id"] not in {
        s["subcontractor_id"] for s in client.get(f"{API}/subcontractors", headers=other.admin.headers).json()
    }
    foreign = _patch(client, other.admin.headers, item, notes="Intrusion")
    assert foreign.status_code == 404
    # Lecture seule pour les rôles de lecture ; refus pour les rôles de terrain.
    finance = api.user(t, "FINANCE")
    assert client.get(f"{API}/subcontractors", headers=finance.headers).status_code == 200
    assert _patch(client, finance.headers, item, notes="Tentative").status_code == 403
    for role, scope, site in (
        ("DISPATCHER", "SITE", "S1"),
        ("MECHANIC", "SITE", "S1"),
        ("WORKSHOP_CHIEF", "TENANT", None),
    ):
        account = api.user(t, role, scope, site) if site else api.user(t, role)
        assert client.get(f"{API}/subcontractors", headers=account.headers).status_code == 403, role
        refused = client.post(
            f"{API}/subcontractors",
            headers=account.headers,
            json={"code": "ST-REFUS", "legal_name": "Refus attendu"},
        )
        assert refused.status_code == 403, role
