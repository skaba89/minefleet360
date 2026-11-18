"""Avancement de mission saisi hors ligne (décisions du 18 novembre 2026) : rejoué si l'état le permet,
antidatage jusqu'à 12 h, événement marqué MOBILE (saisie différée)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_assignment import OffsetClock, World, w  # noqa: F401  (fixture w)
from tests.test_dispatch import _assignment, _event, _mission, _refs


def _new_mission(client: TestClient, w: World) -> str:  # noqa: F811
    created = _mission(client, w, _assignment(client, w), _refs(client, w))
    assert created.status_code == 201, created.text
    return str(created.json()["mission_id"])


def test_deferred_progress_is_accepted_up_to_12_hours_and_marked_mobile(
    client: TestClient,
    w: World,  # noqa: F811
    api: Api,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mid = _new_mission(client, w)
    observed = datetime.now(UTC) + timedelta(minutes=1)
    # Synchronisation 5 h après la saisie terrain.
    monkeypatch.setattr(client.app.state, "clock", OffsetClock(timedelta(hours=5)))  # type: ignore[attr-defined]
    # Nouvelle session ouverte « 5 h plus tard » (le jeton précédent aurait expiré).
    ops = api.login(w.t.code, w.ops.email)
    online_rule = _event(client, w, mid, "DEPARTED", headers=ops, occurred_at=observed.isoformat())
    assert online_rule.status_code == 422 and online_rule.json()["details"][0]["type"] == "out_of_tolerance"
    event_id = str(uuid.uuid4())
    deferred = _event(
        client,
        w,
        mid,
        "DEPARTED",
        headers=ops,
        occurred_at=observed.isoformat(),
        deferred=True,
        client_event_id=event_id,
    )
    assert deferred.status_code == 200, deferred.text
    assert deferred.json()["status"] == "EN_ROUTE_EMPTY"
    events = deferred.json()["events"]
    departed = next(e for e in events if e["event_type"] == "DEPARTED")
    assert departed["source"] == "MOBILE"
    assert datetime.fromisoformat(departed["occurred_at"]) == observed
    # Rejeu du même événement (réponse perdue) : aucun doublon.
    again = _event(
        client,
        w,
        mid,
        "DEPARTED",
        headers=ops,
        occurred_at=observed.isoformat(),
        deferred=True,
        client_event_id=event_id,
    )
    assert again.status_code == 200
    assert sum(1 for e in again.json()["events"] if e["event_type"] == "DEPARTED") == 1
    audit = client.get(
        f"{API}/audit-events",
        headers=api.login(w.t.code, w.t.admin.email),
        params={"action": "mission.departed", "entity_id": mid},
    ).json()["items"]
    assert len(audit) == 1 and audit[0]["after_data"]["deferred"] is True
    # Au-delà de 12 h : refusé même en saisie différée.
    monkeypatch.setattr(client.app.state, "clock", OffsetClock(timedelta(hours=13)))  # type: ignore[attr-defined]
    ops = api.login(w.t.code, w.ops.email)
    late = _event(
        client,
        w,
        mid,
        "ARRIVED_LOADING",
        headers=ops,
        occurred_at=(observed + timedelta(minutes=5)).isoformat(),
        deferred=True,
        client_event_id=str(uuid.uuid4()),
    )
    assert late.status_code == 422 and late.json()["details"][0]["type"] == "out_of_tolerance"


def test_deferred_events_are_refused_when_the_mission_changed(client: TestClient, w: World) -> None:  # noqa: F811
    mid = _new_mission(client, w)
    detail = client.get(f"{API}/missions/{mid}", headers=w.ops.headers).json()
    now = datetime.now(UTC).isoformat()
    # Mission réaffectée entre-temps : l'affectation attendue ne correspond plus.
    reassigned = _event(
        client,
        w,
        mid,
        "DEPARTED",
        occurred_at=now,
        deferred=True,
        client_event_id=str(uuid.uuid4()),
        expected_vehicle_assignment_id=str(uuid.uuid4()),
    )
    assert reassigned.status_code == 422 and reassigned.json()["details"]["reason"] == "reassigned"
    # Affectation attendue exacte : accepté.
    ok = _event(
        client,
        w,
        mid,
        "DEPARTED",
        occurred_at=now,
        deferred=True,
        client_event_id=str(uuid.uuid4()),
        expected_vehicle_assignment_id=detail["vehicle_assignment_id"],
    )
    assert ok.status_code == 200, ok.text
    # État incompatible (ex. DEPARTED déjà appliqué) : refusé, jamais forcé.
    twice = _event(
        client, w, mid, "DEPARTED", occurred_at=now, deferred=True, client_event_id=str(uuid.uuid4())
    )
    assert twice.status_code == 422 and twice.json()["code"] == "MISSION_STATE_INVALID"
    # Décisions (suspension) jamais différées ; identifiant client et heure obligatoires.
    suspend = _event(
        client,
        w,
        mid,
        "SUSPENDED",
        occurred_at=now,
        deferred=True,
        client_event_id=str(uuid.uuid4()),
        reason_code="BREAKDOWN",
    )
    assert suspend.status_code == 422
    missing_id = _event(client, w, mid, "ARRIVED_LOADING", occurred_at=now, deferred=True)
    assert missing_id.status_code == 422
