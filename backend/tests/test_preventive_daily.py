"""Tâche quotidienne `minefleet evaluate-preventive` : règles du bouton, acteur SYSTEM, idempotente."""

from fastapi.testclient import TestClient

from app.cli import main
from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401


def _due_plan(client: TestClient, api: Api, w: World, code: str) -> str:  # noqa: F811
    vehicle = _vehicle(client, w)
    assert (
        client.post(
            f"{API}/preventive-plans",
            headers=w.ops.headers,
            json={"vehicle_id": vehicle, "code": code, "days_interval": 30},
        ).status_code
        == 201
    )
    declared = client.post(
        f"{API}/preventive-declarations",
        headers=w.ops.headers,
        json={"vehicle_id": vehicle, "plan_code": code, "knowledge": "UNKNOWN"},
    ).json()
    chief = api.user(w.t, "WORKSHOP_CHIEF", "SITE", "S1")
    decided = client.post(
        f"{API}/preventive-declarations/{declared['service_declaration_id']}/decide",
        headers=chief.headers,
        json={"decision": "APPROVE"},
    )
    assert decided.status_code == 200, decided.text
    return vehicle


def test_daily_job_creates_dues_once_as_system(client: TestClient, api: Api, w: World, capsys) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    vehicle = _due_plan(client, api, w, "JOB-INIT")

    def dues() -> list[dict]:  # type: ignore[type-arg]
        return client.get(  # type: ignore[no-any-return]
            f"{API}/preventive-dues", headers=w.ops.headers, params={"open_only": True}
        ).json()["items"]

    assert main(["evaluate-preventive", "--dry-run"]) == 0
    assert "simulation" in capsys.readouterr().out
    assert dues() == []  # simulation : rien d'enregistré

    assert main(["evaluate-preventive"]) == 0
    first = dues()
    assert [(d["vehicle_id"], d["trigger_kind"], d["status"]) for d in first] == [(vehicle, "INITIAL", "DUE")]
    assert main(["evaluate-preventive"]) == 0
    assert dues() == first  # rejeu sans doublon

    # Le bouton de l'atelier après la tâche : rien de plus, et aucun OT créé.
    evaluated = client.post(f"{API}/preventive-dues/evaluate", headers=w.ops.headers, json={}).json()
    assert (evaluated["created"], evaluated["already_recorded"]) == (0, 1)

    events = client.get(f"{API}/audit-events", headers=w.t.admin.headers, params={"page_size": 200}).json()[
        "items"
    ]
    created = [e for e in events if e["action"] == "maintenance.due.create"]
    assert len(created) == 1 and created[0]["actor_kind"] == "SYSTEM" and created[0]["actor_user_id"] is None
    assert (
        sum(1 for e in events if e["action"] == "maintenance.due.evaluate" and e["actor_kind"] == "SYSTEM")
        == 2
    )
    work_orders = client.get(f"{API}/work-orders", headers=w.ops.headers).json()
    assert work_orders["total"] == 0
