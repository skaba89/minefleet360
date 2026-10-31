"""Read-only legal registries must enforce roles and tenant/site scope."""

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def test_legal_registries_access_guards(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    direction = api.user(tenant, "DIRECTION", "TENANT")
    manager = api.user(tenant, "OPS_MANAGER", "SITE", "MINE")
    driver = api.user(tenant, "DRIVER", "SITE", "MINE")
    foreign = api.tenant(sites=("OTHER",))
    for endpoint in ("legal-contracts", "insurance-policies"):
        for reader in (direction, manager):
            result = client.get(f"{API}/{endpoint}", headers=reader.headers)
            assert result.status_code == 200, result.text
            assert result.json()["total"] == 0
        denied = client.get(f"{API}/{endpoint}", headers=driver.headers)
        assert denied.status_code == 403
        hidden = client.get(
            f"{API}/{endpoint}",
            headers=manager.headers,
            params={"site_id": str(foreign.sites["OTHER"])},
        )
        assert hidden.status_code == 404
