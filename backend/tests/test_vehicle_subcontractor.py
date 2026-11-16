"""Rattachement d'un engin sous-traité à son organisation sous-traitante (lot 1, tranche 2)."""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import API, Api, TenantFixture


def _subcontractor(client: TestClient, t: TenantFixture) -> dict:  # type: ignore[type-arg]
    resp = client.post(
        f"{API}/subcontractors",
        headers=t.admin.headers,
        json={"code": f"ST-{uuid.uuid4().hex[:6].upper()}", "legal_name": "Transports Fictifs SARL"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()  # type: ignore[no-any-return]


def _end(client: TestClient, t: TenantFixture, item: dict) -> None:  # type: ignore[type-arg]
    resp = client.patch(
        f"{API}/subcontractors/{item['subcontractor_id']}",
        headers={**t.admin.headers, "If-Match": f'"{item["row_version"]}"'},
        json={"status": "ENDED", "status_reason": "Fin du contrat de transport"},
    )
    assert resp.status_code == 200, resp.text


def _vehicle(client: TestClient, t: TenantFixture, **extra: object):  # type: ignore[no-untyped-def]
    category = client.get(f"{API}/vehicle-categories", headers=t.admin.headers).json()[0][
        "vehicle_category_id"
    ]
    return client.post(
        f"{API}/vehicles",
        headers=t.admin.headers,
        json={
            "site_id": str(t.sites["S1"]),
            "vehicle_category_id": category,
            "fleet_number": f"ST-{uuid.uuid4().hex[:6]}",
            **extra,
        },
    )


def _patch(client: TestClient, t: TenantFixture, vehicle: dict, **body: object):  # type: ignore[no-untyped-def,type-arg]
    url = f"{API}/vehicles/{vehicle['vehicle_id']}"
    version = client.get(url, headers=t.admin.headers).headers["ETag"]
    return client.patch(url, headers={**t.admin.headers, "If-Match": version}, json=body)


def test_subcontracted_vehicle_link_lifecycle_and_audit(client: TestClient, api: Api) -> None:
    t = api.tenant()
    partner = _subcontractor(client, t)
    created = _vehicle(
        client, t, ownership_type="SUBCONTRACTED", subcontractor_id=partner["subcontractor_id"]
    )
    assert created.status_code == 201, created.text
    vehicle = created.json()
    assert vehicle["subcontractor_id"] == partner["subcontractor_id"]

    # Changer la propriété sans détacher explicitement : refusé (jamais de modification silencieuse du lien).
    silent = _patch(client, t, vehicle, ownership_type="OWNED")
    assert silent.status_code == 422 and silent.json()["details"][0]["type"] == "must_clear"
    # Détachement explicite avec le changement de propriété : accepté et journalisé.
    detached = _patch(client, t, vehicle, ownership_type="OWNED", subcontractor_id=None)
    assert detached.status_code == 200, detached.text
    assert detached.json()["subcontractor_id"] is None and detached.json()["ownership_type"] == "OWNED"
    audit = client.get(
        f"{API}/audit-events",
        headers=t.admin.headers,
        params={"entity_type": "vehicle", "action": "vehicle.update", "page_size": 50},
    ).json()["items"]
    event = next(e for e in audit if e["entity_id"] == vehicle["vehicle_id"])
    assert "subcontractor_id" in event["changed_fields"]

    # Rattachement d'un engin existant redevenu sous-traité.
    relinked = _patch(
        client, t, vehicle, ownership_type="SUBCONTRACTED", subcontractor_id=partner["subcontractor_id"]
    )
    assert relinked.status_code == 200 and relinked.json()["subcontractor_id"] == partner["subcontractor_id"]
    # Un rattachement existant reste valable si le sous-traitant prend fin ensuite (historique conservé).
    _end(client, t, partner)
    noted = _patch(client, t, relinked.json(), notes="Engin toujours sur site")
    assert noted.status_code == 200 and noted.json()["subcontractor_id"] == partner["subcontractor_id"]


def test_subcontractor_link_is_validated(client: TestClient, api: Api) -> None:
    t, other = api.tenant(), api.tenant()
    partner = _subcontractor(client, t)
    # Engin non sous-traité : rattachement refusé.
    owned = _vehicle(client, t, ownership_type="OWNED", subcontractor_id=partner["subcontractor_id"])
    assert owned.status_code == 422 and owned.json()["details"][0]["type"] == "ownership_mismatch"
    # Sous-traitant inconnu ou d'un autre tenant : indiscernables, refusés.
    unknown = _vehicle(client, t, ownership_type="SUBCONTRACTED", subcontractor_id=str(uuid.uuid4()))
    assert (unknown.status_code, unknown.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    foreign = _subcontractor(client, other)
    stolen = _vehicle(client, t, ownership_type="SUBCONTRACTED", subcontractor_id=foreign["subcontractor_id"])
    assert (stolen.status_code, stolen.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    # Nouveau rattachement à un sous-traitant terminé : refusé.
    ended = _subcontractor(client, t)
    _end(client, t, ended)
    late = _vehicle(client, t, ownership_type="SUBCONTRACTED", subcontractor_id=ended["subcontractor_id"])
    assert late.status_code == 422 and late.json()["details"][0]["type"] == "not_active"
    # Engin sous-traité sans rattachement : toujours permis (aucune reprise automatique du texte libre).
    plain = _vehicle(client, t, ownership_type="SUBCONTRACTED")
    assert plain.status_code == 201 and plain.json()["subcontractor_id"] is None
