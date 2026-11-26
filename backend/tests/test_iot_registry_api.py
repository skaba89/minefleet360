"""HTTP contract for the industrial IoT registry."""

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def test_registry_api(client: TestClient, api: Api) -> None:
    tenant = api.tenant()
    other = api.tenant()
    admin = tenant.admin.headers
    local = api.user(tenant, "OPS_MANAGER", "SITE", "S1").headers
    remote = api.user(tenant, "OPS_MANAGER", "SITE", "S2").headers
    driver = api.user(tenant, "DRIVER", "SITE", "S1").headers
    base = f"{API}/iot"
    assert client.get(f"{base}/gateways").status_code == 401
    assert client.get(f"{base}/gateways", headers=driver).status_code == 403
    assert client.post(f"{base}/manufacturers", headers=local, json={"name": "OEM"}).status_code == 403
    made = client.post(f"{base}/manufacturers", headers=admin, json={"name": "Demo OEM"})
    assert made.status_code == 201, made.text
    manufacturer_id = made.json()["manufacturer_id"]
    assert client.post(f"{base}/manufacturers", headers=admin, json={"name": "demo oem"}).status_code == 409
    body = {
        "site_id": str(tenant.sites["S1"]),
        "manufacturer_id": manufacturer_id,
        "external_id": "G1",
        "model": "Demo",
        "source_kind": "SIMULATED",
    }
    made = client.post(f"{base}/gateways", headers=local, json=body)
    assert made.status_code == 201, made.text
    gateway_id = made.json()["gateway_id"]
    assert client.post(f"{base}/gateways", headers=remote, json=body).status_code == 422
    sensor = {
        "gateway_id": gateway_id,
        "manufacturer_id": manufacturer_id,
        "external_id": "S1",
        "model": "Demo",
        "sensor_kind": "TPMS",
    }
    made = client.post(f"{base}/sensors", headers=local, json=sensor)
    assert made.status_code == 201, made.text
    assert made.json()["source_kind"] == "SIMULATED"
    assert client.post(f"{base}/sensors", headers=remote, json=sensor).status_code == 422
    assert client.post(f"{base}/sensors", headers=other.admin.headers, json=sensor).status_code == 422
    for collection in ("gateways", "sensors"):
        url = f"{base}/{collection}"
        assert client.get(url, headers=local, params={"page_size": 1}).json()["total"] == 1
        assert client.get(url, headers=remote).json()["total"] == 0
        assert client.get(url, headers=other.admin.headers).json()["total"] == 0
        assert client.get(url, headers=admin, params={"tenant_id": str(other.tenant_id)}).status_code == 422
    assert client.get(f"{base}/manufacturers", headers=other.admin.headers).json()["total"] == 0
