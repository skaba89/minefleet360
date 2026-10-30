"""Tests métier du traitement des anomalies de pompes et de l'isolation inter-tenant."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def test_anomaly_case_workflow_and_tenant_isolation(client: TestClient, api: Api) -> None:
    owner = api.tenant(sites=("MINE",))
    outsider = api.tenant(sites=("MINE",))
    manager = api.user(owner, "OPS_MANAGER")
    other = owner.admin.headers
    tank = client.post(
        f"{API}/fuel/tanks",
        headers=other,
        json={
            "site_id": str(owner.sites["MINE"]),
            "code": "CASE-TANK",
            "fuel_type": "DIESEL",
            "capacity_liters": 2000,
        },
    )
    assert tank.status_code == 201, tank.text
    pump = client.post(
        f"{API}/fuel/pumps",
        headers=other,
        json={"fuel_tank_id": tank.json()["fuel_tank_id"], "code": "CASE-PUMP", "name": "Pompe cas"},
    )
    assert pump.status_code == 201, pump.text
    pump_id = pump.json()["fuel_pump_id"]
    start_at = datetime.now(UTC) - timedelta(minutes=10)
    reading_ids = []
    for index, liters in enumerate((100, 130)):
        response = client.post(
            f"{API}/fuel/pumps/{pump_id}/meter-readings",
            headers=other,
            json={
                "cumulative_liters": liters,
                "measured_at": (start_at + timedelta(minutes=5 * index)).isoformat(),
                "source": "MANUAL",
                "source_reference": f"CASE-{index}",
            },
        )
        assert response.status_code == 201, response.text
        reading_ids.append(response.json()["fuel_pump_meter_reading_id"])

    case_path = f"{API}/fuel/pumps/{pump_id}/anomaly-cases"
    body = {"start_reading_id": reading_ids[0], "end_reading_id": reading_ids[1]}
    created = client.post(case_path, headers=other, json=body)
    assert created.status_code == 201, created.text
    case_id = created.json()["fuel_pump_anomaly_case_id"]
    assert client.post(case_path, headers=other, json=body).status_code == 409

    event_path = f"{API}/fuel/anomaly-cases/{case_id}/events"
    assert client.post(event_path, headers=other, json={
        "event_type": "CLOSED", "justification": "Clôture sans traitement"
    }).status_code == 409
    assert client.get(f"{API}/fuel/anomaly-cases", headers=outsider.admin.headers).json()["total"] == 0
    assert client.get(event_path, headers=outsider.admin.headers).status_code == 404
    assert client.post(event_path, headers=outsider.admin.headers, json={
        "event_type": "ACKNOWLEDGED", "justification": "Contrôle extérieur"
    }).status_code == 404

    for event_type in ("ACKNOWLEDGED", "JUSTIFIED"):
        response = client.post(event_path, headers=manager.headers, json={
            "event_type": event_type, "justification": f"Vérification de l'écart : {event_type}"
        })
        assert response.status_code == 201, response.text

    self_close = client.post(event_path, headers=other, json={
        "event_type": "CLOSED", "justification": "Clôture par le créateur"
    })
    assert self_close.status_code == 409, self_close.text
    closed = client.post(event_path, headers=manager.headers, json={
        "event_type": "CLOSED", "justification": "Vérification terminée et documentée"
    })
    assert closed.status_code == 201, closed.text
    assert client.post(event_path, headers=manager.headers, json={
        "event_type": "CLOSED", "justification": "Clôture répétée interdite"
    }).status_code == 409
    history = client.get(event_path, headers=other)
    assert history.status_code == 200, history.text
    assert [item["event_type"] for item in history.json()["items"]] == [
        "ACKNOWLEDGED", "JUSTIFIED", "CLOSED"
    ]
