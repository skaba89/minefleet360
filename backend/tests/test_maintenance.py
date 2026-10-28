"""Lot 3a — signalement de panne, ordres de travail, remise en service (docs/PLAN_LOT3.md)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401  (fixture w)
from tests.test_dispatch import _assignment, _event, _mission, _refs


def _now() -> datetime:
    return datetime.now(UTC)


def _report(client: TestClient, w: World, vehicle: str, headers=None, **extra):  # type: ignore[no-untyped-def]  # noqa: F811
    return client.post(
        f"{API}/work-orders",
        headers=headers or w.dispatcher.headers,
        json={"vehicle_id": vehicle, "symptom_code": "BRAKES", "priority": "HIGH", **extra},
    )


def _act(client: TestClient, kind: str, order_id: str, headers: dict[str, str], **body: object):  # type: ignore[no-untyped-def]
    url = f"{API}/work-orders/{order_id}"
    version = client.get(url, headers=headers).headers["ETag"]
    return client.post(f"{url}/{kind}", headers={**headers, "If-Match": version}, json=body)


def _vehicle_status(client: TestClient, w: World, vehicle: str) -> str:  # noqa: F811
    return str(client.get(f"{API}/vehicles/{vehicle}", headers=w.ops.headers).json()["status"])


def test_breakdown_full_lifecycle(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    """US-3.01 à 3.05 : panne bloquante → atelier → contrôle → remise en service, mission suspendue."""
    chief = api.user(w.t, "WORKSHOP_CHIEF")
    mechanic = api.user(w.t, "MECHANIC", "SITE", "S1")
    assignment = _assignment(client, w)
    vehicle = assignment["vehicle_id"]
    mid = _mission(client, w, assignment, _refs(client, w)).json()["mission_id"]
    assert _event(client, w, mid, "DEPARTED").status_code == 200

    reported = _report(client, w, vehicle, immobilize=True, mission_id=mid, description="Freinage faible")
    assert reported.status_code == 201, reported.text
    order = reported.json()
    oid = order["work_order_id"]
    assert order["status"] == "REQUESTED" and order["reference"].startswith("OT-")
    assert _vehicle_status(client, w, vehicle) == "IMMOBILIZED"
    mission = client.get(f"{API}/missions/{mid}", headers=w.ops.headers).json()
    assert mission["status"] == "SUSPENDED" and mission["status_reason"] == "BREAKDOWN"
    assert mission["events"][-1]["source"] == "SYSTEM"

    ready = (_now() + timedelta(days=2)).isoformat()
    assert (
        _act(client, "decision", oid, chief.headers, action="APPROVE", expected_ready_at=ready).status_code
        == 200
    )
    mechanics = client.get(
        f"{API}/maintenance-mechanics", headers=chief.headers, params={"site_id": order["site_id"]}
    ).json()
    assert str(mechanic.user_id) in {m["user_account_id"] for m in mechanics}
    assigned = _act(
        client, "decision", oid, chief.headers, action="ASSIGN", assigned_to=str(mechanic.user_id)
    )
    assert assigned.status_code == 200 and assigned.json()["status"] == "ASSIGNED"

    started = _act(client, "progress", oid, mechanic.headers, action="START", diagnosis="Plaquettes usées")
    assert started.status_code == 200 and started.json()["status"] == "IN_PROGRESS"
    assert _vehicle_status(client, w, vehicle) == "IN_MAINTENANCE"
    labour = client.post(
        f"{API}/work-orders/{oid}/labour",
        headers=mechanic.headers,
        json={"minutes": 90, "performed_on": date.today().isoformat(), "note": "Dépose"},
    )
    assert labour.status_code == 201 and labour.json()["labour_minutes"] == 90
    no_reason = _act(client, "progress", oid, mechanic.headers, action="AWAIT_PARTS")
    assert (no_reason.status_code, no_reason.json()["code"]) == (422, "STATUS_REASON_REQUIRED")
    assert (
        _act(
            client, "progress", oid, mechanic.headers, action="AWAIT_PARTS", reason_code="PARTS_ORDERED"
        ).status_code
        == 200
    )
    assert _act(client, "progress", oid, mechanic.headers, action="RESUME").status_code == 200
    empty = _act(client, "progress", oid, mechanic.headers, action="SUBMIT")
    assert empty.status_code == 422  # compte rendu obligatoire avant le contrôle
    submitted = _act(
        client, "progress", oid, mechanic.headers, action="SUBMIT", work_done="Plaquettes remplacées"
    )
    assert submitted.json()["status"] == "QUALITY_CHECK"
    assert _act(client, "decision", oid, mechanic.headers, action="QC_PASS").status_code == 403
    failed = _act(client, "decision", oid, chief.headers, action="QC_FAIL", reason_code="FAULT_PERSISTS")
    assert failed.json()["status"] == "IN_PROGRESS"
    _act(client, "progress", oid, mechanic.headers, action="SUBMIT", work_done="Purge du circuit")
    closed = _act(client, "decision", oid, chief.headers, action="QC_PASS")
    assert closed.status_code == 200 and closed.json()["status"] == "CLOSED"
    assert _vehicle_status(client, w, vehicle) == "AVAILABLE"
    events = [e["event_type"] for e in closed.json()["events"]]
    assert events == [
        "REQUESTED",
        "APPROVED",
        "ASSIGNED",
        "STARTED",
        "AWAITING_PARTS",
        "RESUMED",
        "SUBMITTED",
        "QC_FAILED",
        "SUBMITTED",
        "CLOSED",
    ]
    audit = client.get(
        f"{API}/audit-events",
        headers=w.t.admin.headers,
        params={"entity_id": oid, "action": "work_order.qc_pass"},
    ).json()
    assert audit["total"] == 1
    late = client.post(
        f"{API}/work-orders/{oid}/labour",
        headers=mechanic.headers,
        json={"minutes": 10, "performed_on": date.today().isoformat()},
    )
    assert late.status_code == 409  # un OT clôturé n'accepte plus de temps


def test_release_requires_another_person_and_no_other_open_order(
    client: TestClient,
    w: World,  # noqa: F811
    api: Api,
) -> None:
    """RM-114 et D-44 : pas d'auto-validation ; un autre OT ouvert retient le véhicule."""
    chief = api.user(w.t, "WORKSHOP_CHIEF")
    vehicle = _vehicle(client, w)
    first = _report(client, w, vehicle, immobilize=True).json()["work_order_id"]
    second = _report(client, w, vehicle, symptom_code="TYRES").json()["work_order_id"]
    _act(client, "decision", first, chief.headers, action="APPROVE")
    _act(client, "decision", first, chief.headers, action="ASSIGN", assigned_to=str(chief.user_id))
    _act(client, "progress", first, chief.headers, action="START")
    _act(client, "progress", first, chief.headers, action="SUBMIT", work_done="Réparé")
    own = _act(client, "decision", first, chief.headers, action="QC_PASS")
    assert (own.status_code, own.json()["code"]) == (422, "SELF_RELEASE_FORBIDDEN")
    # Réassigner à un collègue après avoir fait le travail ne permet pas de valider soi-même.
    colleague = api.user(w.t, "MECHANIC", "SITE", "S1")
    back = _act(client, "decision", first, chief.headers, action="QC_FAIL", reason_code="INCOMPLETE_WORK")
    assert back.status_code == 200
    _act(client, "decision", first, chief.headers, action="ASSIGN", assigned_to=str(colleague.user_id))
    _act(client, "progress", first, colleague.headers, action="SUBMIT", work_done="Vérifié")
    laundered = _act(client, "decision", first, chief.headers, action="QC_PASS")
    assert (laundered.status_code, laundered.json()["code"]) == (422, "SELF_RELEASE_FORBIDDEN")
    # Compte rendu figé pendant le contrôle (L3A-R-07) ; le retoucher pendant l'intervention exclut aussi
    # de la validation, et l'événement est tracé.
    editor = api.user(w.t, "WORKSHOP_CHIEF")
    frozen = _act(client, "progress", first, editor.headers, action="NOTE", work_done="Réécrit")
    assert frozen.status_code == 409
    _act(client, "decision", first, w.ops.headers, action="QC_FAIL", reason_code="INCOMPLETE_WORK")
    noted = _act(client, "progress", first, editor.headers, action="NOTE", work_done="Réécrit")
    assert noted.status_code == 200 and noted.json()["events"][-1]["event_type"] == "NOTED"
    _act(client, "progress", first, colleague.headers, action="SUBMIT", work_done="Vérifié")
    edited = _act(client, "decision", first, editor.headers, action="QC_PASS")
    assert (edited.status_code, edited.json()["code"]) == (422, "SELF_RELEASE_FORBIDDEN")
    for step in ("APPROVE",):
        _act(client, "decision", second, chief.headers, action=step)
    _act(client, "decision", second, chief.headers, action="ASSIGN", assigned_to=str(chief.user_id))
    _act(client, "progress", second, chief.headers, action="START")
    closed = _act(client, "decision", first, w.ops.headers, action="QC_PASS")
    assert closed.status_code == 200, closed.text
    assert _vehicle_status(client, w, vehicle) == "IN_MAINTENANCE"  # le second OT le retient


def test_invalid_actions_are_refused(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    chief = api.user(w.t, "WORKSHOP_CHIEF")
    mechanic = api.user(w.t, "MECHANIC", "SITE", "S1")
    other_mechanic = api.user(w.t, "MECHANIC", "SITE", "S1")
    vehicle = _vehicle(client, w)
    oid = _report(client, w, vehicle).json()["work_order_id"]
    assert _act(client, "progress", oid, mechanic.headers, action="START").status_code == 403  # non assigné
    assert _act(client, "decision", oid, chief.headers, action="QC_PASS").status_code == 409
    no_reason = _act(client, "decision", oid, chief.headers, action="REJECT")
    assert (no_reason.status_code, no_reason.json()["code"]) == (422, "STATUS_REASON_REQUIRED")
    _act(client, "decision", oid, chief.headers, action="APPROVE")
    not_mechanic = _act(
        client, "decision", oid, chief.headers, action="ASSIGN", assigned_to=str(w.dispatcher.user_id)
    )
    assert (not_mechanic.status_code, not_mechanic.json()["code"]) == (422, "MECHANIC_NOT_ELIGIBLE")
    _act(client, "decision", oid, chief.headers, action="ASSIGN", assigned_to=str(mechanic.user_id))
    stranger = _act(client, "progress", oid, other_mechanic.headers, action="START")
    assert (stranger.status_code, stranger.json()["code"]) == (403, "WORK_ORDER_NOT_ASSIGNEE")
    future = client.post(
        f"{API}/work-orders/{oid}/labour",
        headers=mechanic.headers,
        json={"minutes": 30, "performed_on": (date.today() + timedelta(days=2)).isoformat()},
    )
    assert future.status_code == 422
    other_vehicle = _vehicle(client, w)
    assignment = _assignment(client, w)
    mid = _mission(client, w, assignment, _refs(client, w)).json()["mission_id"]
    wrong_mission = _report(client, w, other_vehicle, mission_id=mid)
    assert (wrong_mission.status_code, wrong_mission.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    cancelled = _act(client, "decision", oid, chief.headers, action="CANCEL", reason_code="DUPLICATE")
    assert cancelled.json()["status"] == "CANCELLED"
    assert _act(client, "decision", oid, chief.headers, action="APPROVE").status_code == 409


def test_numbering_scope_and_append_only(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    first = _report(client, w, _vehicle(client, w)).json()
    second = _report(client, w, _vehicle(client, w)).json()
    assert second["number"] == first["number"] + 1
    s2 = _report(client, w, _vehicle(client, w, "S2"), headers=w.ops.headers).json()
    hidden = client.get(f"{API}/work-orders/{s2['work_order_id']}", headers=w.dispatcher.headers)
    assert hidden.status_code == 404
    listed = client.get(f"{API}/work-orders", headers=w.dispatcher.headers).json()["items"]
    assert s2["work_order_id"] not in {o["work_order_id"] for o in listed}
    s2_vehicle = _report(client, w, s2["vehicle_id"])  # dispatcher du site S1
    assert (s2_vehicle.status_code, s2_vehicle.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    assert client.get(f"{API}/work-orders", headers=api.user(w.t, "FINANCE").headers).status_code == 403
    other_tenant = api.tenant()
    assert client.get(
        f"{API}/work-orders/{first['work_order_id']}", headers=other_tenant.admin.headers
    ).status_code in (403, 404)
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            with pytest.raises(DBAPIError) as refused:
                conn.execute(
                    text("UPDATE work_order_event SET reason = 'OTHER' WHERE work_order_id = :o"),
                    {"o": first["work_order_id"]},
                )
            assert getattr(refused.value.orig, "sqlstate", None) in ("MF001", "42501")
            conn.rollback()
    finally:
        engine.dispose()


# --- Revue sécurité du lot 3a --------------------------------------------------------------------------


def _set_status(client: TestClient, w: World, vehicle: str, status: str, reason: str | None = None) -> None:  # noqa: F811
    url = f"{API}/vehicles/{vehicle}"
    version = client.get(url, headers=w.ops.headers).headers["ETag"]
    body: dict[str, object] = {"status": status}
    if reason:
        body["reason_code"] = reason
    resp = client.post(f"{url}/status", headers={**w.ops.headers, "If-Match": version}, json=body)
    assert resp.status_code == 200, resp.text


def test_rejected_breakdown_releases_vehicle_and_mission_cannot_resume(
    client: TestClient,
    w: World,  # noqa: F811
    api: Api,
) -> None:
    """L3A-R-04 : fausse alerte rejetée → véhicule libéré ; L3A-R-16 : pas de reprise tant qu'immobilisé."""
    chief = api.user(w.t, "WORKSHOP_CHIEF")
    assignment = _assignment(client, w)
    mid = _mission(client, w, assignment, _refs(client, w)).json()["mission_id"]
    assert _event(client, w, mid, "DEPARTED").status_code == 200
    oid = _report(client, w, assignment["vehicle_id"], immobilize=True).json()["work_order_id"]
    resumed = _event(client, w, mid, "RESUMED")
    assert (resumed.status_code, resumed.json()["code"]) == (422, "MISSION_NOT_ELIGIBLE")
    rejected = _act(client, "decision", oid, chief.headers, action="REJECT", reason_code="NOT_A_FAULT")
    assert rejected.status_code == 200
    assert _vehicle_status(client, w, assignment["vehicle_id"]) == "AVAILABLE"
    assert _event(client, w, mid, "RESUMED").status_code == 200


def test_manual_immobilization_is_not_overwritten(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    """L3A-R-05 : un véhicule immobilisé pour une autre raison (accident) n'est pas remis à disposition."""
    chief = api.user(w.t, "WORKSHOP_CHIEF")
    mechanic = api.user(w.t, "MECHANIC", "SITE", "S1")
    vehicle = _vehicle(client, w)
    oid = _report(client, w, vehicle).json()["work_order_id"]
    _act(client, "decision", oid, chief.headers, action="APPROVE")
    _act(client, "decision", oid, chief.headers, action="ASSIGN", assigned_to=str(mechanic.user_id))
    _act(client, "progress", oid, mechanic.headers, action="START")
    _set_status(client, w, vehicle, "IMMOBILIZED", "ACCIDENT")
    _act(client, "progress", oid, mechanic.headers, action="SUBMIT", work_done="Fait")
    closed = _act(client, "decision", oid, chief.headers, action="QC_PASS")
    assert closed.status_code == 200 and closed.json()["status"] == "CLOSED"
    assert _vehicle_status(client, w, vehicle) == "IMMOBILIZED"


def test_awaiting_parts_keeps_its_reason(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    """L3A-R-06 : compte rendu et réassignation possibles en attente de pièces, motif conservé."""
    chief = api.user(w.t, "WORKSHOP_CHIEF")
    mechanic = api.user(w.t, "MECHANIC", "SITE", "S1")
    other = api.user(w.t, "MECHANIC", "SITE", "S1")
    oid = _report(client, w, _vehicle(client, w)).json()["work_order_id"]
    _act(client, "decision", oid, chief.headers, action="APPROVE")
    _act(client, "decision", oid, chief.headers, action="ASSIGN", assigned_to=str(mechanic.user_id))
    _act(client, "progress", oid, mechanic.headers, action="START")
    _act(client, "progress", oid, mechanic.headers, action="AWAIT_PARTS", reason_code="SUPPLIER_DELAY")
    note = _act(client, "progress", oid, mechanic.headers, action="NOTE", parts_note="Pompe commandée")
    assert note.status_code == 200 and note.json()["status_reason"] == "SUPPLIER_DELAY"
    moved = _act(client, "decision", oid, chief.headers, action="ASSIGN", assigned_to=str(other.user_id))
    assert moved.status_code == 200 and moved.json()["status_reason"] == "SUPPLIER_DELAY"
    assigned = [e for e in moved.json()["events"] if e["event_type"] == "ASSIGNED"]
    assert [e["subject_user_id"] for e in assigned] == [str(mechanic.user_id), str(other.user_id)]


def test_moved_vehicle_daily_cap_and_names(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    """L3A-R-09 : véhicule déplacé ; L3A-R-11 : 24 h par jour ; L3A-R-13 : noms réservés à l'atelier."""
    chief = api.user(w.t, "WORKSHOP_CHIEF")
    mechanic = api.user(w.t, "MECHANIC", "SITE", "S1")
    vehicle = _vehicle(client, w)
    oid = _report(client, w, vehicle).json()["work_order_id"]
    _act(client, "decision", oid, chief.headers, action="APPROVE")
    _act(client, "decision", oid, chief.headers, action="ASSIGN", assigned_to=str(mechanic.user_id))
    seen_by_dispatcher = client.get(f"{API}/work-orders/{oid}", headers=w.dispatcher.headers).json()
    assert seen_by_dispatcher["assigned_name"] is None
    assert seen_by_dispatcher["assigned_to"] is None and seen_by_dispatcher["reported_by"] is None
    assert seen_by_dispatcher["labour"] is None
    assert all(e["actor_user_id"] is None for e in seen_by_dispatcher["events"])
    assert all(e["actor_name"] is None for e in seen_by_dispatcher["events"])
    assert client.get(f"{API}/work-orders/{oid}", headers=chief.headers).json()["assigned_name"]
    today = date.today().isoformat()
    for minutes, expected in ((960, 201), (480, 201), (1, 422)):
        resp = client.post(
            f"{API}/work-orders/{oid}/labour",
            headers=mechanic.headers,
            json={"minutes": minutes, "performed_on": today},
        )
        assert resp.status_code == expected, resp.text
    url = f"{API}/vehicles/{vehicle}"
    version = client.get(url, headers=w.ops.headers).headers["ETag"]
    patched = client.patch(
        url, headers={**w.ops.headers, "If-Match": version}, json={"site_id": str(w.t.sites["S2"])}
    )
    assert patched.status_code == 200, patched.text
    start = _act(client, "progress", oid, chief.headers, action="START")
    assert (start.status_code, start.json()["code"]) == (409, "WORK_ORDER_STATE_INVALID")


def test_reject_only_lifts_its_own_immobilization(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    """Revue automatique : une immobilisation posée par quelqu'un d'autre n'est jamais levée."""
    chief = api.user(w.t, "WORKSHOP_CHIEF")
    vehicle = _vehicle(client, w)
    _set_status(client, w, vehicle, "IMMOBILIZED", "BREAKDOWN")
    oid = _report(client, w, vehicle, immobilize=True).json()["work_order_id"]
    assert (
        _act(client, "decision", oid, chief.headers, action="REJECT", reason_code="DUPLICATE").status_code
        == 200
    )
    assert _vehicle_status(client, w, vehicle) == "IMMOBILIZED"
