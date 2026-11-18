"""Avancement de mission saisi hors ligne (décisions du 18 novembre 2026) : rejoué si l'état le permet,
antidatage jusqu'à 12 h, événement marqué MOBILE (saisie différée).

Le jeton de session suit l'horloge système : la tolérance est testée en réduisant les bornes, pas en avançant
l'horloge de plusieurs heures."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from tests.conftest import API
from tests.test_assignment import World, w  # noqa: F401  (fixture w)
from tests.test_dispatch import _assignment, _event, _mission, _refs


def _new_mission(client: TestClient, w: World) -> str:  # noqa: F811
    created = _mission(client, w, _assignment(client, w), _refs(client, w))
    assert created.status_code == 201, created.text
    return str(created.json()["mission_id"])


def test_deferred_progress_uses_the_offline_tolerance_and_is_marked_mobile(
    client: TestClient,
    w: World,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mid = _new_mission(client, w)
    events = client.get(f"{API}/missions/{mid}", headers=w.ops.headers).json()["events"]
    created = next(e["occurred_at"] for e in events if e["event_type"] == "CREATED")
    observed = datetime.fromisoformat(created) + timedelta(milliseconds=1)
    # Tolérance en ligne réduite à presque rien : l'étape « observée » juste après la création est trop
    # ancienne pour une saisie en ligne, mais dans la tolérance hors ligne (12 h par défaut).
    monkeypatch.setattr(get_settings(), "assignment_backdate_tolerance", timedelta(microseconds=1))
    online_rule = _event(client, w, mid, "DEPARTED", occurred_at=observed.isoformat())
    assert online_rule.status_code == 422 and online_rule.json()["details"][0]["type"] == "out_of_tolerance"
    event_id = str(uuid.uuid4())
    deferred = _event(
        client, w, mid, "DEPARTED", occurred_at=observed.isoformat(), deferred=True, client_event_id=event_id
    )
    assert deferred.status_code == 200, deferred.text
    assert deferred.json()["status"] == "EN_ROUTE_EMPTY"
    departed = next(e for e in deferred.json()["events"] if e["event_type"] == "DEPARTED")
    assert departed["source"] == "MOBILE"
    assert datetime.fromisoformat(departed["occurred_at"]) == observed
    # Rejeu du même événement (réponse perdue) : aucun doublon.
    again = _event(
        client, w, mid, "DEPARTED", occurred_at=observed.isoformat(), deferred=True, client_event_id=event_id
    )
    assert again.status_code == 200
    assert sum(1 for e in again.json()["events"] if e["event_type"] == "DEPARTED") == 1
    audit = client.get(
        f"{API}/audit-events",
        headers=w.t.admin.headers,
        params={"action": "mission.departed", "entity_id": mid},
    ).json()["items"]
    assert len(audit) == 1 and audit[0]["after_data"]["deferred"] is True
    # Au-delà de la tolérance hors ligne : refusé même en saisie différée.
    monkeypatch.setattr(get_settings(), "mission_offline_backdate_tolerance", timedelta(microseconds=1))
    late = _event(
        client,
        w,
        mid,
        "ARRIVED_LOADING",
        occurred_at=(observed + timedelta(milliseconds=1)).isoformat(),
        deferred=True,
        client_event_id=str(uuid.uuid4()),
    )
    assert late.status_code == 422 and late.json()["details"][0]["type"] == "out_of_tolerance"


def test_offline_tolerance_default_is_12_hours() -> None:
    assert get_settings().mission_offline_backdate_tolerance == timedelta(hours=12)


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
    assert reassigned.status_code == 409 and reassigned.json()["details"]["reason"] == "reassigned"
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
    assert twice.status_code == 409 and twice.json()["code"] == "MISSION_STATE_INVALID"
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
