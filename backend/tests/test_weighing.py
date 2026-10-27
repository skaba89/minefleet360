"""Lot 2b — pesées, corrections, saisie dégradée et indicateurs (docs/PLAN_LOT2.md §7)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from tests.conftest import API, Api
from tests.test_assignment import World, w  # noqa: F401  (fixture w)
from tests.test_dispatch import _assignment, _event, _mission, _refs


def _now() -> datetime:
    return datetime.now(UTC)


def _weighbridge(client: TestClient, w: World, site: str = "S1") -> str:  # noqa: F811
    code = f"PONT-{uuid.uuid4().hex[:6].upper()}"
    resp = client.post(
        f"{API}/site-locations",
        headers=w.t.admin.headers,
        json={"site_id": str(w.t.sites[site]), "code": code, "name": f"Pont {code}", "kind": "WEIGHBRIDGE"},
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["site_location_id"])


def _set_payload(client: TestClient, w: World, vehicle_id: str, kg: int) -> None:  # noqa: F811
    url = f"{API}/vehicles/{vehicle_id}"
    version = client.get(url, headers=w.t.admin.headers).headers["ETag"]
    resp = client.patch(
        url, headers={**w.t.admin.headers, "If-Match": version}, json={"rated_payload_kg": kg}
    )
    assert resp.status_code == 200, resp.text


def _loaded_mission(client: TestClient, w: World, site: str = "S1", steps: tuple[str, ...] = ()):  # type: ignore[no-untyped-def]  # noqa: F811
    """Mission sur une affectation active, avancée jusqu'au chargement terminé (rotation pesable)."""
    assignment = _assignment(client, w, site)
    mission = _mission(client, w, assignment, _refs(client, w, site)).json()
    for event in ("DEPARTED", "ARRIVED_LOADING", "LOADED", *steps):
        resp = _event(client, w, mission["mission_id"], event)
        assert resp.status_code == 200, (event, resp.text)
    detail = client.get(f"{API}/missions/{mission['mission_id']}", headers=w.ops.headers).json()
    return assignment, detail


def _ticket(
    rotation_id: str, weighbridge: str, number: str | None = None, **extra: object
) -> dict[str, object]:
    return {
        "rotation_id": rotation_id,
        "weighbridge_location_id": weighbridge,
        "ticket_number": number or f"T-{uuid.uuid4().hex[:8]}",
        "weighed_at": _now().isoformat(),
        "gross_kg": 52_000,
        "tare_kg": 18_000,
        **extra,
    }


def test_measured_ticket_is_unique_and_resend_safe(client: TestClient, w: World) -> None:  # noqa: F811
    _, mission = _loaded_mission(client, w)
    rotation = mission["rotations"][0]["rotation_id"]
    bridge = _weighbridge(client, w)
    body = _ticket(rotation, bridge, "T-0001")
    first = client.post(f"{API}/weighing-tickets", headers=w.dispatcher.headers, json=body)
    assert first.status_code == 201, first.text
    ticket = first.json()
    assert (ticket["net_kg"], ticket["status"], ticket["source"]) == (34_000, "VALID", "WEIGHBRIDGE")
    assert "driver" not in str(ticket)  # aucune donnée nominative du conducteur dans une pesée
    again = client.post(f"{API}/weighing-tickets", headers=w.dispatcher.headers, json=body)
    assert again.status_code == 200 and again.json()["weighing_ticket_id"] == ticket["weighing_ticket_id"]
    reused = client.post(f"{API}/weighing-tickets", headers=w.ops.headers, json={**body, "gross_kg": 60_000})
    assert (reused.status_code, reused.json()["code"]) == (409, "DUPLICATE_TICKET_NUMBER")
    second = client.post(f"{API}/weighing-tickets", headers=w.ops.headers, json=_ticket(rotation, bridge))
    assert (second.status_code, second.json()["code"]) == (409, "ROTATION_ALREADY_WEIGHED")
    audit = client.get(
        f"{API}/audit-events",
        headers=w.t.admin.headers,
        params={"entity_id": ticket["weighing_ticket_id"], "action": "weighing_ticket.create"},
    ).json()
    assert audit["total"] == 1


def test_ticket_requires_loaded_rotation_and_valid_values(client: TestClient, w: World) -> None:  # noqa: F811
    assignment = _assignment(client, w)
    refs = _refs(client, w)
    mid = _mission(client, w, assignment, refs).json()["mission_id"]
    for event in ("DEPARTED", "ARRIVED_LOADING"):
        assert _event(client, w, mid, event).status_code == 200
    loading = client.get(f"{API}/missions/{mid}", headers=w.ops.headers).json()["rotations"][0]["rotation_id"]
    bridge = _weighbridge(client, w)
    early = client.post(f"{API}/weighing-tickets", headers=w.ops.headers, json=_ticket(loading, bridge))
    assert (early.status_code, early.json()["code"]) == (409, "ROTATION_NOT_WEIGHABLE")

    _, mission = _loaded_mission(client, w)
    rotation = mission["rotations"][0]["rotation_id"]
    cases = {
        "not_a_weighbridge": _ticket(rotation, refs["origin"]),
        "other_site_bridge": _ticket(rotation, _weighbridge(client, w, "S2")),
        "gross_below_tare": _ticket(rotation, bridge, gross_kg=10_000, tare_kg=18_000),
        "future": _ticket(rotation, bridge, weighed_at=(_now() + timedelta(hours=1)).isoformat()),
        "before_loading": _ticket(rotation, bridge, weighed_at=(_now() - timedelta(hours=2)).isoformat()),
        "degraded_without_reason": _ticket(rotation, bridge, source="MANUAL_DEGRADED"),
        "reason_without_degraded": _ticket(rotation, bridge, degraded_reason="POWER_OUTAGE"),
        "net_typed": {**_ticket(rotation, bridge), "net_kg": 1},
    }
    for label, body in cases.items():
        resp = client.post(f"{API}/weighing-tickets", headers=w.ops.headers, json=body)
        assert resp.status_code == 422, (label, resp.text)
    foreign_rotation = client.post(
        f"{API}/weighing-tickets", headers=w.ops.headers, json=_ticket(str(uuid.uuid4()), bridge)
    )
    assert (foreign_rotation.status_code, foreign_rotation.json()["code"]) == (422, "REFERENCE_NOT_FOUND")


def test_correction_voids_original_and_keeps_history(client: TestClient, w: World) -> None:  # noqa: F811
    _, mission = _loaded_mission(client, w, steps=("ARRIVED_UNLOADING", "UNLOADED"))
    rotation = mission["rotations"][0]["rotation_id"]
    bridge = _weighbridge(client, w)
    original = client.post(
        f"{API}/weighing-tickets", headers=w.dispatcher.headers, json=_ticket(rotation, bridge, "T-7")
    ).json()
    url = f"{API}/weighing-tickets/{original['weighing_ticket_id']}"
    body = {k: v for k, v in _ticket(rotation, bridge, "T-7").items() if k != "rotation_id"}
    denied = client.post(
        f"{url}/correct", headers=w.dispatcher.headers, json={**body, "reason_code": "ENTRY_ERROR"}
    )
    assert denied.status_code == 403  # correction réservée au responsable des opérations
    fixed = client.post(
        f"{url}/correct",
        headers=w.ops.headers,
        json={**body, "tare_kg": 20_000, "reason_code": "ENTRY_ERROR"},
    )
    assert fixed.status_code == 201, fixed.text
    assert fixed.json()["replaces_ticket_id"] == original["weighing_ticket_id"]
    assert (fixed.json()["net_kg"], fixed.json()["status"]) == (32_000, "VALID")
    voided = client.get(url, headers=w.ops.headers).json()
    assert (
        voided["status"] == "VOIDED" and voided["replaced_by_ticket_id"] == fixed.json()["weighing_ticket_id"]
    )
    assert voided["decisions"][0]["reason"] == "ENTRY_ERROR"
    twice = client.post(f"{url}/correct", headers=w.ops.headers, json={**body, "reason_code": "ENTRY_ERROR"})
    assert (twice.status_code, twice.json()["code"]) == (409, "WEIGHING_STATE_INVALID")
    listed = client.get(
        f"{API}/weighing-tickets", headers=w.ops.headers, params={"mission_id": mission["mission_id"]}
    ).json()
    assert listed["total"] == 2
    valid_only = client.get(
        f"{API}/weighing-tickets",
        headers=w.ops.headers,
        params={"mission_id": mission["mission_id"], "status": "VALID"},
    ).json()
    assert [t["weighing_ticket_id"] for t in valid_only["items"]] == [fixed.json()["weighing_ticket_id"]]
    # Annulation simple puis nouvelle pesée de la même rotation : possible, l'annulé reste consultable.
    gone = client.post(
        f"{API}/weighing-tickets/{fixed.json()['weighing_ticket_id']}/void",
        headers=w.ops.headers,
        json={"reason_code": "WRONG_VEHICLE"},
    )
    assert gone.status_code == 200 and gone.json()["status"] == "VOIDED"
    renewed = client.post(f"{API}/weighing-tickets", headers=w.ops.headers, json=_ticket(rotation, bridge))
    assert renewed.status_code == 201, renewed.text


def test_degraded_entry_needs_approval_by_someone_else(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    _, mission = _loaded_mission(client, w)
    rotation = mission["rotations"][0]["rotation_id"]
    bridge = _weighbridge(client, w)
    degraded = client.post(
        f"{API}/weighing-tickets",
        headers=w.ops.headers,
        json=_ticket(rotation, bridge, source="MANUAL_DEGRADED", degraded_reason="WEIGHBRIDGE_DOWN"),
    ).json()
    assert degraded["status"] == "PENDING_APPROVAL"
    url = f"{API}/weighing-tickets/{degraded['weighing_ticket_id']}/approve"
    own = client.post(url, headers=w.ops.headers, json={})
    assert (own.status_code, own.json()["code"]) == (422, "SELF_APPROVAL_FORBIDDEN")
    assert client.post(url, headers=w.dispatcher.headers, json={}).status_code == 403
    other = api.user(w.t, "OPS_MANAGER")
    approved = client.post(url, headers=other.headers, json={})
    assert approved.status_code == 200 and approved.json()["status"] == "VALID"
    assert approved.json()["decisions"][0]["decided_by"] == str(other.user_id)
    again = client.post(url, headers=other.headers, json={})
    assert (again.status_code, again.json()["code"]) == (409, "WEIGHING_STATE_INVALID")


def test_overload_is_flagged_against_rated_payload(client: TestClient, w: World) -> None:  # noqa: F811
    assignment, mission = _loaded_mission(client, w)
    _set_payload(client, w, assignment["vehicle_id"], 30_000)  # 34 t nets > 30 t × 110 %
    bridge = _weighbridge(client, w)
    ticket = client.post(
        f"{API}/weighing-tickets",
        headers=w.ops.headers,
        json=_ticket(mission["rotations"][0]["rotation_id"], bridge),
    ).json()
    assert ticket["overload"] is True and ticket["rated_payload_kg"] == 30_000
    hse = client.get(f"{API}/weighing-tickets", headers=w.ops.headers, params={"overload": "true"}).json()
    assert ticket["weighing_ticket_id"] in {t["weighing_ticket_id"] for t in hse["items"]}


def test_indicators_keep_measured_pending_and_estimated_apart(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    assignment = _assignment(client, w)
    _set_payload(client, w, assignment["vehicle_id"], 40_000)
    refs = _refs(client, w)
    mid = _mission(client, w, assignment, refs).json()["mission_id"]
    assert _event(client, w, mid, "DEPARTED").status_code == 200
    for _ in range(3):
        for event in ("ARRIVED_LOADING", "LOADED", "ARRIVED_UNLOADING", "UNLOADED"):
            assert _event(client, w, mid, event).status_code == 200, event
    assert _event(client, w, mid, "COMPLETED").status_code == 200
    rotations = client.get(f"{API}/missions/{mid}", headers=w.ops.headers).json()["rotations"]
    bridge = _weighbridge(client, w)
    client.post(
        f"{API}/weighing-tickets", headers=w.ops.headers, json=_ticket(rotations[0]["rotation_id"], bridge)
    )
    client.post(
        f"{API}/weighing-tickets",
        headers=w.ops.headers,
        json=_ticket(
            rotations[1]["rotation_id"],
            bridge,
            source="MANUAL_DEGRADED",
            degraded_reason="POWER_OUTAGE",
            tare_kg=20_000,
        ),
    )
    resp = client.get(
        f"{API}/dispatch-indicators",
        headers=api.user(w.t, "DIRECTION").headers,
        params={"site_id": str(w.t.sites["S1"])},
    )
    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json()["rows"] if r["material_id"] == refs["material"])
    assert (row["missions_completed"], row["rotations_completed"]) == (1, 3)
    assert (row["measured_net_kg"], row["measured_rotations"]) == (34_000, 1)
    assert (row["pending_net_kg"], row["pending_rotations"]) == (32_000, 1)
    assert (row["estimated_kg"], row["estimated_rotations"]) == (40_000, 1)
    assert row["short_cycles"] == 3  # cycles déclarés en quelques secondes : signalés comme suspects
    too_long = client.get(
        f"{API}/dispatch-indicators",
        headers=w.ops.headers,
        params={"period_start": (_now() - timedelta(days=200)).isoformat()},
    )
    assert too_long.status_code == 422
    assert "gps" not in resp.text.lower()


def test_weighing_scope_and_append_only(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    _, mission = _loaded_mission(client, w, "S2")
    ticket = client.post(
        f"{API}/weighing-tickets",
        headers=w.ops.headers,
        json=_ticket(mission["rotations"][0]["rotation_id"], _weighbridge(client, w, "S2")),
    ).json()
    url = f"{API}/weighing-tickets/{ticket['weighing_ticket_id']}"
    assert client.get(url, headers=w.dispatcher.headers).status_code == 404  # dispatcher du site S1
    listed = client.get(f"{API}/weighing-tickets", headers=w.dispatcher.headers).json()
    assert ticket["weighing_ticket_id"] not in {t["weighing_ticket_id"] for t in listed["items"]}
    s2_rotation = client.post(
        f"{API}/weighing-tickets",
        headers=w.dispatcher.headers,
        json=_ticket(mission["rotations"][0]["rotation_id"], _weighbridge(client, w)),
    )
    assert (s2_rotation.status_code, s2_rotation.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    assert client.get(url, headers=api.user(w.t, "WORKSHOP_CHIEF").headers).status_code == 403
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            for statement in (
                "UPDATE weighing_ticket SET gross_kg = gross_kg + 1 WHERE weighing_ticket_id = :i",
                "DELETE FROM weighing_ticket WHERE weighing_ticket_id = :i",
            ):
                with pytest.raises(DBAPIError) as refused:
                    conn.execute(text(statement), {"i": ticket["weighing_ticket_id"]})
                assert getattr(refused.value.orig, "sqlstate", None) in ("MF001", "42501")
                conn.rollback()
                conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
    finally:
        engine.dispose()


# --- Suites de la revue du lot 2a ----------------------------------------------------------------------


def test_new_cycle_refused_once_assignment_closed(client: TestClient, w: World) -> None:  # noqa: F811
    """L2A-R-07 : le cycle en cours se termine, mais aucun nouveau chargement sur une affectation close."""
    assignment, mission = _loaded_mission(client, w)
    url = f"{API}/vehicle-assignments/{assignment['vehicle_assignment_id']}"
    version = client.get(url, headers=w.ops.headers).headers["ETag"]
    closed = client.post(f"{url}/complete", headers={**w.ops.headers, "If-Match": version}, json={})
    assert closed.status_code == 200, closed.text
    for event in ("ARRIVED_UNLOADING", "UNLOADED"):
        assert _event(client, w, mission["mission_id"], event).status_code == 200, event
    refused = _event(client, w, mission["mission_id"], "ARRIVED_LOADING")
    assert (refused.status_code, refused.json()["code"]) == (422, "MISSION_NOT_ELIGIBLE")
    assert _event(client, w, mission["mission_id"], "COMPLETED").status_code == 200


def test_rotation_cap(client: TestClient, w: World, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """L2A-R-04 : plafond de rotations par mission."""
    monkeypatch.setattr(get_settings(), "mission_max_rotations", 1)
    _, mission = _loaded_mission(client, w, steps=("ARRIVED_UNLOADING", "UNLOADED"))
    capped = _event(client, w, mission["mission_id"], "ARRIVED_LOADING")
    assert (capped.status_code, capped.json()["code"]) == (409, "MISSION_STATE_INVALID")
    assert capped.json()["details"]["reason"] == "max_rotations"


def test_mission_creation_resend_is_idempotent(client: TestClient, w: World) -> None:  # noqa: F811
    """L2A-R-08 : un renvoi de création avec le même identifiant rend la même mission."""
    assignment = _assignment(client, w)
    refs = _refs(client, w)
    key = str(uuid.uuid4())
    body = {
        "vehicle_assignment_id": assignment["vehicle_assignment_id"],
        "origin_location_id": refs["origin"],
        "destination_location_id": refs["destination"],
        "material_id": refs["material"],
        "planned_start": _now().isoformat(),
        "client_request_id": key,
    }
    first = client.post(f"{API}/missions", headers=w.ops.headers, json=body)
    again = client.post(f"{API}/missions", headers=w.ops.headers, json=body)
    assert first.status_code == again.status_code == 201
    assert first.json()["mission_id"] == again.json()["mission_id"]
    other = _assignment(client, w)
    clash = client.post(
        f"{API}/missions",
        headers=w.ops.headers,
        json={**body, "vehicle_assignment_id": other["vehicle_assignment_id"]},
    )
    assert (clash.status_code, clash.json()["code"]) == (409, "CONFLICT")
