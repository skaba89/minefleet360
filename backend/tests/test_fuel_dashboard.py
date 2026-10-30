"""Tableau de bord carburant : agrégats fiables et isolation tenant/site."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_fuel_anomaly_workflow import _open_case
from tests.test_fuel_pumps import _assigned_vehicle_and_driver, _tank


def _period(now: datetime) -> dict[str, str]:
    return {
        "from": (now - timedelta(days=1)).isoformat(),
        "to": (now + timedelta(minutes=1)).isoformat(),
    }


def test_fuel_dashboard_aggregates_approved_flows_and_scopes_sites(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE", "PORT"))
    outsider = api.tenant(sites=("MINE",))
    now = datetime.now(UTC)
    tank = _tank(client, tenant.admin.headers, tenant.sites["MINE"])
    receipt = client.post(
        f"{API}/fuel/tanks/{tank['fuel_tank_id']}/receipts",
        headers=tenant.admin.headers,
        json={
            "liters": "500.000",
            "reference": "BL-DASH-001",
            "occurred_at": (now - timedelta(hours=2)).isoformat(),
        },
    )
    assert receipt.status_code == 201, receipt.text
    port_tank = _tank(client, tenant.admin.headers, tenant.sites["PORT"])
    port_receipt = client.post(
        f"{API}/fuel/tanks/{port_tank['fuel_tank_id']}/receipts",
        headers=tenant.admin.headers,
        json={
            "liters": "200.000",
            "reference": "BL-DASH-PORT-001",
            "occurred_at": (now - timedelta(hours=2)).isoformat(),
        },
    )
    assert port_receipt.status_code == 201, port_receipt.text

    ops_headers, vehicle_id, driver_id, meter_kind = _assigned_vehicle_and_driver(client, api, tenant)
    issue_payload: dict[str, object] = {
        "fuel_tank_id": tank["fuel_tank_id"],
        "vehicle_id": vehicle_id,
        "driver_id": driver_id,
        "liters": "80.000",
        "requested_at": (now - timedelta(hours=1)).isoformat(),
    }
    if meter_kind is not None:
        issue_payload.update({"meter_kind": meter_kind, "meter_value": "100.0"})
    issue = client.post(f"{API}/fuel/issues", headers=ops_headers, json=issue_payload)
    assert issue.status_code == 201, issue.text
    approved = client.post(
        f"{API}/fuel/issues/{issue.json()['fuel_issue_id']}/decision",
        headers=tenant.admin.headers,
        json={"decision": "APPROVED"},
    )
    assert approved.status_code == 200, approved.text

    params = _period(now)
    response = client.get(f"{API}/fuel/dashboard", headers=tenant.admin.headers, params=params)
    assert response.status_code == 200, response.text
    data = response.json()
    assert Decimal(data["distributed_liters"]) == Decimal("80.000")
    assert Decimal(data["received_liters"]) == Decimal("700.000")
    assert data["open_anomaly_cases"] == 0
    assert data["closed_anomaly_cases"] == 0
    assert data["active_stock_alerts"] == 0
    assert data["vehicle_consumption"] == [
        {
            "vehicle_id": vehicle_id,
            "vehicle_fleet_number": "POMPE-VEH-01",
            "site_id": str(tenant.sites["MINE"]),
            "liters": "80.000",
        }
    ]
    assert data["site_consumption"] == [
        {
            "site_id": str(tenant.sites["MINE"]),
            "site_code": "MINE",
            "site_name": "Site MINE",
            "liters": "80.000",
        }
    ]
    assert len(data["daily_trend"]) == 2
    assert sum(Decimal(row["distributed_liters"]) for row in data["daily_trend"]) == Decimal("80.000")

    port_only = client.get(
        f"{API}/fuel/dashboard",
        headers=tenant.admin.headers,
        params={**params, "site_id": str(tenant.sites["PORT"])},
    )
    assert port_only.status_code == 200, port_only.text
    assert Decimal(port_only.json()["distributed_liters"]) == 0
    assert Decimal(port_only.json()["received_liters"]) == Decimal("200.000")
    assert port_only.json()["vehicle_consumption"] == []

    fuel_manager = api.user(tenant, "FUEL_MANAGER", scope="SITE", site="MINE")
    scoped = client.get(f"{API}/fuel/dashboard", headers=fuel_manager.headers, params=params)
    assert scoped.status_code == 200, scoped.text
    assert Decimal(scoped.json()["distributed_liters"]) == Decimal("80.000")
    assert Decimal(scoped.json()["received_liters"]) == Decimal("500.000")

    hidden_site = client.get(
        f"{API}/fuel/dashboard",
        headers=outsider.admin.headers,
        params={**params, "site_id": str(tenant.sites["MINE"])},
    )
    assert hidden_site.status_code == 404, hidden_site.text
    outsider_dashboard = client.get(f"{API}/fuel/dashboard", headers=outsider.admin.headers, params=params)
    assert outsider_dashboard.status_code == 200, outsider_dashboard.text
    assert Decimal(outsider_dashboard.json()["distributed_liters"]) == 0


def test_fuel_dashboard_reports_anomaly_backlog_and_resolution(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    now = datetime.now(UTC)
    open_case = _open_case(
        client,
        headers=tenant.admin.headers,
        site_id=tenant.sites["MINE"],
        prefix="DASH-OPEN",
    )
    closed_case = _open_case(
        client,
        headers=tenant.admin.headers,
        site_id=tenant.sites["MINE"],
        prefix="DASH-CLOSED",
    )
    event_path = f"{API}/fuel/anomaly-cases/{closed_case['fuel_pump_anomaly_case_id']}/events"
    for event_type in ("ACKNOWLEDGED", "JUSTIFIED"):
        event = client.post(
            event_path,
            headers=tenant.admin.headers,
            json={
                "event_type": event_type,
                "justification": f"Traitement dashboard {event_type.lower()}",
            },
        )
        assert event.status_code == 201, event.text
    closer = api.user(tenant, "FUEL_MANAGER", scope="SITE", site="MINE")
    closed = client.post(
        event_path,
        headers=closer.headers,
        json={"event_type": "CLOSED", "justification": "Contrôle contradictoire finalisé"},
    )
    assert closed.status_code == 201, closed.text

    response = client.get(f"{API}/fuel/dashboard", headers=tenant.admin.headers, params=_period(now))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["open_anomaly_cases"] == 1
    assert data["closed_anomaly_cases"] == 1
    assert Decimal(data["qualified_anomaly_variance_liters"]) == Decimal("60.000")
    assert Decimal(data["average_resolution_hours"]) >= 0
    assert open_case["status"] == "OPEN"


def test_fuel_dashboard_rejects_invalid_period(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    now = datetime.now(UTC)
    reversed_period = client.get(
        f"{API}/fuel/dashboard",
        headers=tenant.admin.headers,
        params={"from": now.isoformat(), "to": (now - timedelta(days=1)).isoformat()},
    )
    assert reversed_period.status_code == 422, reversed_period.text
    assert reversed_period.json()["code"] == "VALIDATION_ERROR"

    oversized = client.get(
        f"{API}/fuel/dashboard",
        headers=tenant.admin.headers,
        params={
            "from": (now - timedelta(days=367)).isoformat(),
            "to": now.isoformat(),
        },
    )
    assert oversized.status_code == 422, oversized.text
    assert oversized.json()["code"] == "VALIDATION_ERROR"
