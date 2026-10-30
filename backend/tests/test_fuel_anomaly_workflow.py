"""Tests métier du traitement des anomalies de pompes et de l'isolation inter-tenant."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import API, Api


def _open_case(
    client: TestClient,
    *,
    headers: dict[str, str],
    site_id: object,
    prefix: str,
) -> dict[str, object]:
    tank = client.post(
        f"{API}/fuel/tanks",
        headers=headers,
        json={
            "site_id": str(site_id),
            "code": f"{prefix}-TANK",
            "fuel_type": "DIESEL",
            "capacity_liters": 2000,
        },
    )
    assert tank.status_code == 201, tank.text
    pump = client.post(
        f"{API}/fuel/pumps",
        headers=headers,
        json={
            "fuel_tank_id": tank.json()["fuel_tank_id"],
            "code": f"{prefix}-PUMP",
            "name": f"Pompe {prefix}",
        },
    )
    assert pump.status_code == 201, pump.text
    pump_id = pump.json()["fuel_pump_id"]
    started = datetime.now(UTC) - timedelta(minutes=10)
    reading_ids: list[str] = []
    for index, liters in enumerate((100, 130)):
        reading = client.post(
            f"{API}/fuel/pumps/{pump_id}/meter-readings",
            headers=headers,
            json={
                "cumulative_liters": liters,
                "measured_at": (started + timedelta(minutes=5 * index)).isoformat(),
                "source": "MANUAL",
                "source_reference": f"{prefix}-{index}",
            },
        )
        assert reading.status_code == 201, reading.text
        reading_ids.append(reading.json()["fuel_pump_meter_reading_id"])
    opened = client.post(
        f"{API}/fuel/pumps/{pump_id}/anomaly-cases",
        headers=headers,
        json={"start_reading_id": reading_ids[0], "end_reading_id": reading_ids[1]},
    )
    assert opened.status_code == 201, opened.text
    return opened.json()


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
    assert created.json()["status"] == "OPEN"
    assert created.json()["meter_delta_liters"] == "30.000"
    assert created.json()["approved_issue_liters"] == "0.000"
    assert created.json()["variance_liters"] == "30.000"
    assert created.json()["variance_percent"] == "100.000"
    assert created.json()["tolerance_liters"] == "5.000"
    assert created.json()["tolerance_percent"] == "1.000"
    assert created.json()["qualification_reason"] == "METER_VOLUME_EXCEEDS_APPROVED_ISSUES"
    assert client.post(case_path, headers=other, json=body).status_code == 409

    event_path = f"{API}/fuel/anomaly-cases/{case_id}/events"
    assert (
        client.post(
            event_path,
            headers=other,
            json={"event_type": "CLOSED", "justification": "Clôture sans traitement"},
        ).status_code
        == 409
    )
    assert client.get(f"{API}/fuel/anomaly-cases", headers=outsider.admin.headers).json()["total"] == 0
    assert client.get(event_path, headers=outsider.admin.headers).status_code == 404
    assert (
        client.post(
            event_path,
            headers=outsider.admin.headers,
            json={"event_type": "ACKNOWLEDGED", "justification": "Contrôle extérieur"},
        ).status_code
        == 404
    )

    for event_type in ("ACKNOWLEDGED", "JUSTIFIED"):
        response = client.post(
            event_path,
            headers=manager.headers,
            json={"event_type": event_type, "justification": f"Vérification de l'écart : {event_type}"},
        )
        assert response.status_code == 201, response.text
        filtered = client.get(
            f"{API}/fuel/anomaly-cases",
            headers=other,
            params={"status": event_type},
        )
        assert filtered.status_code == 200, filtered.text
        assert filtered.json()["total"] == 1
        assert filtered.json()["items"][0]["fuel_pump_anomaly_case_id"] == case_id
    listed = client.get(f"{API}/fuel/anomaly-cases", headers=other)
    assert listed.status_code == 200, listed.text
    matching = next(c for c in listed.json()["items"] if c["fuel_pump_anomaly_case_id"] == case_id)
    assert matching["status"] == "JUSTIFIED"

    self_close = client.post(
        event_path, headers=other, json={"event_type": "CLOSED", "justification": "Clôture par le créateur"}
    )
    assert self_close.status_code == 409, self_close.text
    closed = client.post(
        event_path,
        headers=manager.headers,
        json={"event_type": "CLOSED", "justification": "Vérification terminée et documentée"},
    )
    assert closed.status_code == 201, closed.text
    listed = client.get(f"{API}/fuel/anomaly-cases", headers=other)
    matching = next(c for c in listed.json()["items"] if c["fuel_pump_anomaly_case_id"] == case_id)
    assert matching["status"] == "CLOSED"
    assert (
        client.post(
            event_path,
            headers=manager.headers,
            json={"event_type": "CLOSED", "justification": "Clôture répétée interdite"},
        ).status_code
        == 409
    )
    history = client.get(event_path, headers=other)
    assert history.status_code == 200, history.text
    assert [item["event_type"] for item in history.json()["items"]] == ["ACKNOWLEDGED", "JUSTIFIED", "CLOSED"]


def test_anomaly_status_filter_paginates_with_tenant_and_site_scope(client: TestClient, api: Api) -> None:
    owner = api.tenant(sites=("S1", "S2"))
    outsider = api.tenant(sites=("S1",))
    manager = api.user(owner, "OPS_MANAGER")
    site_manager = api.user(owner, "OPS_MANAGER", "SITE", "S1")
    first_open = _open_case(
        client,
        headers=owner.admin.headers,
        site_id=owner.sites["S1"],
        prefix="FILTER-S1-A",
    )
    second_open = _open_case(
        client,
        headers=owner.admin.headers,
        site_id=owner.sites["S1"],
        prefix="FILTER-S1-B",
    )
    closed_case = _open_case(
        client,
        headers=owner.admin.headers,
        site_id=owner.sites["S2"],
        prefix="FILTER-S2",
    )
    event_path = f"{API}/fuel/anomaly-cases/{closed_case['fuel_pump_anomaly_case_id']}/events"
    for event_type in ("ACKNOWLEDGED", "JUSTIFIED", "CLOSED"):
        event = client.post(
            event_path,
            headers=manager.headers,
            json={
                "event_type": event_type,
                "justification": f"Traitement complet du filtre {event_type}",
            },
        )
        assert event.status_code == 201, event.text

    first_page = client.get(
        f"{API}/fuel/anomaly-cases",
        headers=site_manager.headers,
        params={"status": "OPEN", "page": 1, "page_size": 1},
    )
    second_page = client.get(
        f"{API}/fuel/anomaly-cases",
        headers=site_manager.headers,
        params={"status": "OPEN", "page": 2, "page_size": 1},
    )
    assert first_page.status_code == second_page.status_code == 200
    assert first_page.json()["total"] == second_page.json()["total"] == 2
    visible_ids = {
        first_page.json()["items"][0]["fuel_pump_anomaly_case_id"],
        second_page.json()["items"][0]["fuel_pump_anomaly_case_id"],
    }
    assert visible_ids == {
        first_open["fuel_pump_anomaly_case_id"],
        second_open["fuel_pump_anomaly_case_id"],
    }
    assert {first_page.json()["items"][0]["status"], second_page.json()["items"][0]["status"]} == {"OPEN"}

    site_closed = client.get(
        f"{API}/fuel/anomaly-cases",
        headers=site_manager.headers,
        params={"status": "CLOSED"},
    )
    assert site_closed.status_code == 200
    assert site_closed.json()["total"] == 0
    tenant_closed = client.get(
        f"{API}/fuel/anomaly-cases",
        headers=manager.headers,
        params={"status": "CLOSED"},
    )
    assert tenant_closed.status_code == 200
    assert tenant_closed.json()["total"] == 1
    assert (
        tenant_closed.json()["items"][0]["fuel_pump_anomaly_case_id"]
        == closed_case["fuel_pump_anomaly_case_id"]
    )
    assert tenant_closed.json()["items"][0]["status"] == "CLOSED"

    forbidden_site = client.get(
        f"{API}/fuel/anomaly-cases",
        headers=site_manager.headers,
        params={"site_id": str(owner.sites["S2"]), "status": "OPEN"},
    )
    assert forbidden_site.status_code == 404
    foreign = client.get(
        f"{API}/fuel/anomaly-cases",
        headers=outsider.admin.headers,
        params={"status": "OPEN"},
    )
    assert foreign.status_code == 200
    assert foreign.json()["total"] == 0
    assert (
        client.get(
            f"{API}/fuel/anomaly-cases",
            headers=manager.headers,
            params={"status": "UNKNOWN"},
        ).status_code
        == 422
    )


def test_simultaneous_acknowledgements_only_create_one_event(client: TestClient, api: Api) -> None:
    """Le verrou transactionnel sérialise deux décisions sur un même dossier."""
    owner = api.tenant(sites=("MINE",))
    headers = owner.admin.headers
    tank = client.post(
        f"{API}/fuel/tanks",
        headers=headers,
        json={
            "site_id": str(owner.sites["MINE"]),
            "code": "CONCURRENT",
            "fuel_type": "DIESEL",
            "capacity_liters": 1000,
        },
    )
    assert tank.status_code == 201, tank.text
    pump = client.post(
        f"{API}/fuel/pumps",
        headers=headers,
        json={"fuel_tank_id": tank.json()["fuel_tank_id"], "code": "CONCURRENT", "name": "Pompe parallèle"},
    )
    assert pump.status_code == 201, pump.text
    pump_id = pump.json()["fuel_pump_id"]
    started = datetime.now(UTC) - timedelta(minutes=10)
    ids = []
    for index, liters in enumerate((20, 40)):
        response = client.post(
            f"{API}/fuel/pumps/{pump_id}/meter-readings",
            headers=headers,
            json={
                "cumulative_liters": liters,
                "measured_at": (started + timedelta(minutes=index * 5)).isoformat(),
                "source": "MANUAL",
                "source_reference": f"CONCURRENT-{index}",
            },
        )
        assert response.status_code == 201, response.text
        ids.append(response.json()["fuel_pump_meter_reading_id"])
    opened = client.post(
        f"{API}/fuel/pumps/{pump_id}/anomaly-cases",
        headers=headers,
        json={"start_reading_id": ids[0], "end_reading_id": ids[1]},
    )
    assert opened.status_code == 201, opened.text
    path = f"{API}/fuel/anomaly-cases/{opened.json()['fuel_pump_anomaly_case_id']}/events"

    def acknowledge(_: int) -> int:
        response = client.post(
            path,
            headers=headers,
            json={"event_type": "ACKNOWLEDGED", "justification": "Contrôle de concurrence effectué"},
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(acknowledge, range(2)))
    assert statuses == [201, 409]
    history = client.get(path, headers=headers)
    assert history.status_code == 200, history.text
    assert history.json()["total"] == 1


def test_simultaneous_qualification_only_opens_one_case(client: TestClient, api: Api) -> None:
    """Le verrou de pompe sérialise la qualification avant la contrainte unique."""
    owner = api.tenant(sites=("MINE",))
    headers = owner.admin.headers
    tank = client.post(
        f"{API}/fuel/tanks",
        headers=headers,
        json={
            "site_id": str(owner.sites["MINE"]),
            "code": "QUALIFY-CONCURRENT",
            "fuel_type": "DIESEL",
            "capacity_liters": 1000,
        },
    )
    assert tank.status_code == 201, tank.text
    pump = client.post(
        f"{API}/fuel/pumps",
        headers=headers,
        json={
            "fuel_tank_id": tank.json()["fuel_tank_id"],
            "code": "QUALIFY-CONCURRENT",
            "name": "Pompe qualification parallèle",
        },
    )
    assert pump.status_code == 201, pump.text
    pump_id = pump.json()["fuel_pump_id"]
    started = datetime.now(UTC) - timedelta(minutes=10)
    reading_ids: list[str] = []
    for index, liters in enumerate((100, 130)):
        response = client.post(
            f"{API}/fuel/pumps/{pump_id}/meter-readings",
            headers=headers,
            json={
                "cumulative_liters": liters,
                "measured_at": (started + timedelta(minutes=index * 5)).isoformat(),
                "source": "MANUAL",
                "source_reference": f"QUALIFY-CONCURRENT-{index}",
            },
        )
        assert response.status_code == 201, response.text
        reading_ids.append(response.json()["fuel_pump_meter_reading_id"])
    path = f"{API}/fuel/pumps/{pump_id}/anomaly-cases"
    body = {"start_reading_id": reading_ids[0], "end_reading_id": reading_ids[1]}

    def qualify(_: int) -> int:
        return client.post(path, headers=headers, json=body).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(qualify, range(2)))
    assert statuses == [201, 409]
    listed = client.get(f"{API}/fuel/anomaly-cases", headers=headers)
    assert listed.status_code == 200, listed.text
    matching = [item for item in listed.json()["items"] if item["fuel_pump_id"] == pump_id]
    assert len(matching) == 1
