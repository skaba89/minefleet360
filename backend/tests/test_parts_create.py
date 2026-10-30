"""Création du catalogue et des magasins : portée site, validation et doublons."""

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def test_create_part_and_store_with_site_permissions(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    manager = api.user(tenant, "STOREKEEPER", "SITE", "MINE")
    driver = api.user(tenant, "DRIVER", "SITE", "MINE")
    part = {"code": "FILTRE-01", "name": "Filtre hydraulique", "unit": "EACH"}
    created = client.post(f"{API}/parts", headers=manager.headers, json=part)
    assert created.status_code == 201, created.text
    assert created.json()["code"] == part["code"]
    duplicate = client.post(f"{API}/parts", headers=manager.headers, json=part)
    assert duplicate.status_code == 409
    assert client.post(f"{API}/parts", headers=driver.headers, json=part).status_code == 403

    store = {"site_id": str(tenant.sites["MINE"]), "code": "MAG-01", "name": "Magasin central"}
    created_store = client.post(f"{API}/part-stores", headers=manager.headers, json=store)
    assert created_store.status_code == 201, created_store.text
    assert created_store.json()["site_id"] == store["site_id"]
    assert client.post(f"{API}/part-stores", headers=manager.headers, json=store).status_code == 409
    assert client.post(f"{API}/part-stores", headers=driver.headers, json=store).status_code == 403

    other_tenant = api.tenant(sites=("OTHER",))
    foreign_store = {**store, "site_id": str(other_tenant.sites["OTHER"])}
    assert client.post(f"{API}/part-stores", headers=manager.headers, json=foreign_store).status_code == 422
