from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def _tank(client: TestClient, headers: dict[str, str], site_id: object) -> dict[str, object]:
    response = client.post(
        f"{API}/fuel/tanks",
        headers=headers,
        json={
            "site_id": str(site_id),
            "code": "CUVE-01",
            "fuel_type": "DIESEL",
            "capacity_liters": "5000.000",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _pump(client: TestClient, headers: dict[str, str], tank_id: object) -> dict[str, object]:
    response = client.post(
        f"{API}/fuel/pumps",
        headers=headers,
        json={
            "fuel_tank_id": str(tank_id),
            "code": "POMPE-01",
            "name": "Pompe principale",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_pump_meter_readings_are_monotonic_and_idempotent(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    tank = _tank(client, tenant.admin.headers, tenant.sites["MINE"])
    pump = _pump(client, tenant.admin.headers, tank["fuel_tank_id"])
    pump_id = pump["fuel_pump_id"]
    first_at = datetime.now(UTC) - timedelta(minutes=10)

    first_payload = {
        "cumulative_liters": "1000.000",
        "measured_at": first_at.isoformat(),
        "source": "MANUAL",
        "source_reference": "lecture-001",
    }
    first = client.post(
        f"{API}/fuel/pumps/{pump_id}/meter-readings",
        headers=tenant.admin.headers,
        json=first_payload,
    )
    assert first.status_code == 201, first.text
    assert Decimal(first.json()["cumulative_liters"]) == Decimal("1000.000")

    replay = client.post(
        f"{API}/fuel/pumps/{pump_id}/meter-readings",
        headers=tenant.admin.headers,
        json=first_payload,
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["fuel_pump_meter_reading_id"] == first.json()["fuel_pump_meter_reading_id"]

    second = client.post(
        f"{API}/fuel/pumps/{pump_id}/meter-readings",
        headers=tenant.admin.headers,
        json={
            "cumulative_liters": "1075.500",
            "measured_at": (first_at + timedelta(minutes=5)).isoformat(),
            "source": "DEVICE",
            "source_reference": "tracker:000002",
        },
    )
    assert second.status_code == 201, second.text

    decreasing = client.post(
        f"{API}/fuel/pumps/{pump_id}/meter-readings",
        headers=tenant.admin.headers,
        json={
            "cumulative_liters": "1075.499",
            "measured_at": (first_at + timedelta(minutes=6)).isoformat(),
            "source": "MANUAL",
            "source_reference": "lecture-003",
        },
    )
    assert decreasing.status_code == 409, decreasing.text

    readings = client.get(
        f"{API}/fuel/pumps/{pump_id}/meter-readings",
        headers=tenant.admin.headers,
    )
    assert readings.status_code == 200, readings.text
    assert readings.json()["total"] == 2
    assert readings.json()["items"][0]["source_reference"] == "tracker:000002"


def test_pumps_are_tenant_scoped(client: TestClient, api: Api) -> None:
    owner = api.tenant(sites=("MINE",))
    outsider = api.tenant(sites=("MINE",))
    tank = _tank(client, owner.admin.headers, owner.sites["MINE"])
    pump = _pump(client, owner.admin.headers, tank["fuel_tank_id"])

    owner_list = client.get(f"{API}/fuel/pumps", headers=owner.admin.headers)
    assert owner_list.status_code == 200, owner_list.text
    assert owner_list.json()["total"] == 1

    outsider_list = client.get(f"{API}/fuel/pumps", headers=outsider.admin.headers)
    assert outsider_list.status_code == 200, outsider_list.text
    assert outsider_list.json()["items"] == []

    hidden = client.get(
        f"{API}/fuel/pumps/{pump['fuel_pump_id']}/meter-readings",
        headers=outsider.admin.headers,
    )
    assert hidden.status_code == 404, hidden.text
