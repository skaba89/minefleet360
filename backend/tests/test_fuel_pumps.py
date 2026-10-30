from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import API, Api, TenantFixture


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


def _assigned_vehicle_and_driver(
    client: TestClient, api: Api, tenant: TenantFixture
) -> tuple[dict[str, str], str, str, str | None]:
    admin = tenant.admin.headers
    site_id = tenant.sites["MINE"]
    hr = api.user(tenant, "HR")
    ops = api.user(tenant, "OPS_MANAGER")
    category = client.get(f"{API}/vehicle-categories", headers=admin).json()[0]
    vehicle = client.post(
        f"{API}/vehicles",
        headers=admin,
        json={
            "site_id": str(site_id),
            "vehicle_category_id": category["vehicle_category_id"],
            "fleet_number": "POMPE-VEH-01",
            "fuel_type": "DIESEL",
        },
    )
    assert vehicle.status_code == 201, vehicle.text
    driver = client.post(
        f"{API}/drivers",
        headers=hr.headers,
        json={
            "site_id": str(site_id),
            "employee_number": "POMPE-DRV-01",
            "last_name": "Test",
            "first_name": "Pompe",
        },
    )
    assert driver.status_code == 201, driver.text
    driver_id = driver.json()["driver_id"]
    license_code = (category.get("required_license_categories") or ["C"])[0]
    license_response = client.post(
        f"{API}/drivers/{driver_id}/licenses",
        headers=hr.headers,
        json={
            "license_number": "POMPE-PERMIS-01",
            "category_code": license_code,
            "issue_date": "2020-01-01",
            "expiry_date": "2035-01-01",
        },
    )
    assert license_response.status_code == 201, license_response.text
    qualification = client.post(
        f"{API}/drivers/{driver_id}/qualifications",
        headers=hr.headers,
        json={
            "qualification_type": "DRIVING_AUTHORIZATION",
            "vehicle_category_id": category["vehicle_category_id"],
            "valid_from": "2020-01-01",
        },
    )
    assert qualification.status_code == 201, qualification.text
    assignment = client.post(
        f"{API}/vehicle-assignments",
        headers=ops.headers,
        json={
            "vehicle_id": vehicle.json()["vehicle_id"],
            "driver_id": driver_id,
            "valid_from": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        },
    )
    assert assignment.status_code == 201, assignment.text
    meter_kind = (
        "ODOMETER" if category["has_odometer"] else "HOUR_METER" if category["has_hour_meter"] else None
    )
    return ops.headers, vehicle.json()["vehicle_id"], driver_id, meter_kind


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


def test_pump_reconciliation_uses_only_approved_issues(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    tank = _tank(client, tenant.admin.headers, tenant.sites["MINE"])
    pump = _pump(client, tenant.admin.headers, tank["fuel_tank_id"])
    pump_id = pump["fuel_pump_id"]
    ops_headers, vehicle_id, driver_id, meter_kind = _assigned_vehicle_and_driver(client, api, tenant)
    now = datetime.now(UTC)
    first_at = now - timedelta(minutes=10)
    issue_at = now

    received = client.post(
        f"{API}/fuel/tanks/{tank['fuel_tank_id']}/receipts",
        headers=tenant.admin.headers,
        json={
            "liters": "500.000",
            "reference": "BL-POMPE-RECO-01",
            "occurred_at": (now - timedelta(minutes=20)).isoformat(),
        },
    )
    assert received.status_code == 201, received.text

    first = client.post(
        f"{API}/fuel/pumps/{pump_id}/meter-readings",
        headers=tenant.admin.headers,
        json={
            "cumulative_liters": "1000.000",
            "measured_at": first_at.isoformat(),
            "source": "MANUAL",
            "source_reference": "RECO-001",
        },
    )
    assert first.status_code == 201, first.text

    issue_payload: dict[str, object] = {
        "fuel_tank_id": tank["fuel_tank_id"],
        "fuel_pump_id": pump_id,
        "vehicle_id": vehicle_id,
        "driver_id": driver_id,
        "liters": "50.000",
        "requested_at": issue_at.isoformat(),
    }
    if meter_kind is not None:
        issue_payload.update({"meter_kind": meter_kind, "meter_value": "100.0"})
    issue = client.post(f"{API}/fuel/issues", headers=ops_headers, json=issue_payload)
    assert issue.status_code == 201, issue.text
    assert issue.json()["fuel_pump_id"] == pump_id
    approved = client.post(
        f"{API}/fuel/issues/{issue.json()['fuel_issue_id']}/decision",
        headers=tenant.admin.headers,
        json={"decision": "APPROVED"},
    )
    assert approved.status_code == 200, approved.text

    for value, at, reference in (
        ("1052.000", issue_at + timedelta(seconds=1), "RECO-002"),
        ("1072.000", issue_at + timedelta(seconds=2), "RECO-003"),
    ):
        reading = client.post(
            f"{API}/fuel/pumps/{pump_id}/meter-readings",
            headers=tenant.admin.headers,
            json={
                "cumulative_liters": value,
                "measured_at": at.isoformat(),
                "source": "MANUAL",
                "source_reference": reference,
            },
        )
        assert reading.status_code == 201, reading.text

    reconciliation = client.get(
        f"{API}/fuel/pumps/{pump_id}/reconciliations",
        headers=tenant.admin.headers,
    )
    assert reconciliation.status_code == 200, reconciliation.text
    data = reconciliation.json()
    assert data["total"] == 2
    latest, matched = data["items"]
    assert Decimal(latest["meter_delta_liters"]) == Decimal("20.000")
    assert Decimal(latest["approved_issue_liters"]) == Decimal("0")
    assert latest["is_anomaly"] is True
    assert Decimal(matched["meter_delta_liters"]) == Decimal("52.000")
    assert Decimal(matched["approved_issue_liters"]) == Decimal("50.000")
    assert Decimal(matched["variance_liters"]) == Decimal("2.000")
    assert matched["is_anomaly"] is False
