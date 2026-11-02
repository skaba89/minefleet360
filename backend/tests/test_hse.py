"""Lot HSE-1 — incidents, enquête, actions correctives et clôture (docs/LIVRAISON_HSE1.md)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from tests.conftest import API, Account, Api, TenantFixture


@dataclass
class World:
    t: TenantFixture
    other: TenantFixture
    hse: Account
    hse2: Account
    hse_s2: Account
    ops: Account
    dispatcher: Account
    mechanic: Account
    other_hse: Account
    vehicle: str
    vehicle_s2: str


def _vehicle(client: TestClient, t: TenantFixture, site: str, number: str) -> str:
    category = client.get(f"{API}/vehicle-categories", headers=t.admin.headers).json()[0][
        "vehicle_category_id"
    ]
    resp = client.post(
        f"{API}/vehicles",
        headers=t.admin.headers,
        json={"site_id": str(t.sites[site]), "vehicle_category_id": category, "fleet_number": number},
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["vehicle_id"])


@pytest.fixture(scope="module")
def w(api: Api, client: TestClient) -> World:
    t, other = api.tenant(), api.tenant()
    return World(
        t=t,
        other=other,
        hse=api.user(t, "HSE"),
        hse2=api.user(t, "HSE"),
        hse_s2=api.user(t, "HSE", "SITE", "S2"),
        ops=api.user(t, "OPS_MANAGER"),
        dispatcher=api.user(t, "DISPATCHER", "SITE", "S1"),
        mechanic=api.user(t, "MECHANIC", "SITE", "S1"),
        other_hse=api.user(other, "HSE"),
        vehicle=_vehicle(client, t, "S1", "HSE-001"),
        vehicle_s2=_vehicle(client, t, "S2", "HSE-002"),
    )


def _report(client: TestClient, w: World, headers: dict[str, str] | None = None, **extra: object):  # type: ignore[no-untyped-def]
    body: dict[str, object] = {
        "site_id": str(w.t.sites["S1"]),
        "category": "VEHICLE_COLLISION",
        "severity": "HIGH",
        "title": "Accrochage en fosse",
        "description": "Un camion a heurté un merlon en marche arrière, sans blessé.",
        "occurred_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
        **extra,
    }
    return client.post(f"{API}/hse/incidents", headers=headers or w.dispatcher.headers, json=body)


def _transition(client: TestClient, incident_id: str, headers: dict[str, str], **body: object):  # type: ignore[no-untyped-def]
    url = f"{API}/hse/incidents/{incident_id}"
    version = client.get(url, headers=headers).headers["ETag"]
    return client.post(f"{url}/transition", headers={**headers, "If-Match": version}, json=body)


def _add_action(client: TestClient, incident_id: str, w: World, owner: Account, **extra: object):  # type: ignore[no-untyped-def]
    return client.post(
        f"{API}/hse/incidents/{incident_id}/actions",
        headers=w.hse.headers,
        json={
            "title": "Baliser la zone de recul",
            "owner_user_id": str(owner.user_id),
            "due_date": (date.today() + timedelta(days=7)).isoformat(),
            **extra,
        },
    )


def _action_post(client: TestClient, item: dict, kind: str, headers: dict[str, str], **body: object):  # type: ignore[no-untyped-def,type-arg]
    return client.post(
        f"{API}/hse/corrective-actions/{item['hse_corrective_action_id']}/{kind}",
        headers={**headers, "If-Match": f'"{item["row_version"]}"'},
        json=body,
    )


def test_full_lifecycle_with_separation_of_duties(client: TestClient, w: World) -> None:
    reported = _report(client, w, vehicle_id=w.vehicle, injured_count=0, location_note="Fosse nord")
    assert reported.status_code == 201, reported.text
    incident = reported.json()
    iid = incident["hse_incident_id"]
    assert incident["status"] == "REPORTED" and incident["reference"].startswith("HSE-")
    assert incident["vehicle_fleet_number"] == "HSE-001"
    assert reported.headers["ETag"] == f'"{incident["row_version"]}"'

    assert _transition(client, iid, w.hse.headers, action="START_INVESTIGATION").status_code == 200
    noted = _transition(client, iid, w.hse.headers, action="NOTE", root_cause="Absence de guide au recul")
    assert noted.status_code == 200 and noted.json()["root_cause"] == "Absence de guide au recul"

    # Incident grave : pas de clôture sans action corrective vérifiée.
    early = _transition(client, iid, w.hse.headers, action="CLOSE")
    assert early.status_code == 422 and early.json()["code"] == "HSE_CORRECTIVE_ACTION_REQUIRED"

    owners = client.get(f"{API}/hse/incidents/{iid}/action-owners", headers=w.hse.headers).json()
    assert str(w.dispatcher.user_id) in {o["user_account_id"] for o in owners}
    assert str(w.mechanic.user_id) not in {o["user_account_id"] for o in owners}
    created = _add_action(client, iid, w, w.dispatcher)
    assert created.status_code == 201, created.text
    action = created.json()
    assert action["status"] == "OPEN" and action["overdue"] is False

    pending = _transition(client, iid, w.hse.headers, action="CLOSE")
    assert pending.status_code == 409 and pending.json()["code"] == "HSE_ACTIONS_PENDING"

    # Seul le responsable déclare l'action réalisée.
    not_owner = _action_post(client, action, "complete", w.ops.headers, completion_note="Fait par un autre")
    assert not_owner.status_code == 403 and not_owner.json()["code"] == "HSE_NOT_ACTION_OWNER"
    mine = client.get(f"{API}/hse/corrective-actions", headers=w.dispatcher.headers, params={"mine": True})
    assert [a["hse_corrective_action_id"] for a in mine.json()["items"]] == [
        action["hse_corrective_action_id"]
    ]
    done = _action_post(
        client, action, "complete", w.dispatcher.headers, completion_note="Balises posées et guide désigné"
    )
    assert done.status_code == 200 and done.json()["status"] == "DONE", done.text

    # Réouverture motivée puis nouvelle réalisation.
    reopened = _action_post(
        client, done.json(), "decision", w.hse.headers, action="REOPEN", reason_code="INCOMPLETE"
    )
    assert reopened.status_code == 200 and reopened.json()["status"] == "OPEN"
    done = _action_post(
        client,
        reopened.json(),
        "complete",
        w.dispatcher.headers,
        completion_note="Balisage complété côté est",
    )
    assert done.status_code == 200
    stale = _action_post(client, reopened.json(), "decision", w.hse.headers, action="VERIFY")
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    verified = _action_post(client, done.json(), "decision", w.hse.headers, action="VERIFY")
    assert verified.status_code == 200 and verified.json()["verified_by"] == str(w.hse.user_id)

    closed = _transition(
        client, iid, w.hse.headers, action="CLOSE", investigation_summary="Guide obligatoire."
    )
    assert closed.status_code == 200, closed.text
    body = closed.json()
    assert body["status"] == "CLOSED" and body["closed_by"] == str(w.hse.user_id)
    assert [e["event_type"] for e in body["events"]] == [
        "REPORTED",
        "INVESTIGATION_STARTED",
        "NOTED",
        "ACTION_ADDED",
        "ACTION_COMPLETED",
        "ACTION_REOPENED",
        "ACTION_COMPLETED",
        "ACTION_VERIFIED",
        "CLOSED",
    ]
    again = _transition(client, iid, w.hse.headers, action="CANCEL", reason_code="DUPLICATE")
    assert again.status_code == 409 and again.json()["code"] == "HSE_INCIDENT_STATE_INVALID"

    audit = client.get(
        f"{API}/audit-events", headers=w.t.admin.headers, params={"action": "hse.incident.close"}
    ).json()["items"]
    assert any(e["entity_id"] == iid for e in audit)


def test_reporter_cannot_close_and_self_verification_is_refused(client: TestClient, w: World) -> None:
    incident = _report(client, w, headers=w.hse.headers, severity="LOW", category="NEAR_MISS").json()
    iid = incident["hse_incident_id"]
    _transition(client, iid, w.hse.headers, action="START_INVESTIGATION")
    action = _add_action(client, iid, w, w.hse2).json()
    done = _action_post(
        client, action, "complete", w.hse2.headers, completion_note="Consigne affichée au poste"
    ).json()
    selfcheck = _action_post(client, done, "decision", w.hse2.headers, action="VERIFY")
    assert selfcheck.status_code == 422 and selfcheck.json()["code"] == "HSE_SELF_VERIFICATION_FORBIDDEN"
    assert _action_post(client, done, "decision", w.hse.headers, action="VERIFY").status_code == 200

    own = _transition(client, iid, w.hse.headers, action="CLOSE", root_cause="Consigne non affichée")
    assert own.status_code == 422 and own.json()["code"] == "HSE_SELF_CLOSURE_FORBIDDEN"
    assert (
        _transition(
            client, iid, w.hse2.headers, action="CLOSE", root_cause="Consigne non affichée"
        ).status_code
        == 200
    )


def test_cancel_requires_reason_and_no_live_action(client: TestClient, w: World) -> None:
    iid = _report(client, w, severity="LOW").json()["hse_incident_id"]
    missing = _transition(client, iid, w.hse.headers, action="CANCEL")
    assert missing.status_code == 422 and missing.json()["code"] == "STATUS_REASON_REQUIRED"
    action = _add_action(client, iid, w, w.ops).json()
    blocked = _transition(client, iid, w.hse.headers, action="CANCEL", reason_code="DUPLICATE")
    assert blocked.status_code == 409
    cancelled = _action_post(
        client, action, "decision", w.hse.headers, action="CANCEL", reason_code="DUPLICATE"
    )
    assert cancelled.status_code == 200
    done = _transition(client, iid, w.hse.headers, action="CANCEL", reason_code="DUPLICATE")
    assert done.status_code == 200 and done.json()["status_reason"] == "DUPLICATE"


def test_input_validation(client: TestClient, w: World) -> None:
    future = _report(client, w, occurred_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat())
    assert future.status_code == 422
    # Tolérance de dérive d'horloge du terminal : quelques minutes d'avance sont acceptées.
    skew = _report(client, w, occurred_at=(datetime.now(UTC) + timedelta(minutes=3)).isoformat())
    assert skew.status_code == 201
    other_site_vehicle = _report(client, w, vehicle_id=w.vehicle_s2)
    assert (
        other_site_vehicle.status_code == 422 and other_site_vehicle.json()["code"] == "REFERENCE_NOT_FOUND"
    )
    unknown = _report(client, w, extra_field="x")
    assert unknown.status_code == 422
    iid = skew.json()["hse_incident_id"]
    past = _add_action(client, iid, w, w.ops, due_date="2020-01-01")
    assert past.status_code == 422
    mechanic = _add_action(client, iid, w, w.mechanic)
    assert mechanic.status_code == 422 and mechanic.json()["code"] == "HSE_OWNER_NOT_ELIGIBLE"
    foreign_owner = _add_action(client, iid, w, w.other_hse)
    assert foreign_owner.status_code == 422
    wrong = _transition(client, iid, w.hse.headers, action="START_INVESTIGATION", reason_code="DUPLICATE")
    assert wrong.status_code == 422
    note = _transition(client, iid, w.hse.headers, action="NOTE", root_cause="x")
    assert note.status_code == 409 and note.json()["code"] == "HSE_INCIDENT_STATE_INVALID"


def test_mechanic_reports_but_cannot_read(client: TestClient, w: World) -> None:
    created = _report(client, w, headers=w.mechanic.headers, severity="MEDIUM")
    assert created.status_code == 201
    listed = client.get(f"{API}/hse/incidents", headers=w.mechanic.headers)
    assert listed.status_code == 403


def test_site_scope_and_tenant_isolation(client: TestClient, w: World) -> None:
    iid = _report(client, w).json()["hse_incident_id"]
    action = _add_action(client, iid, w, w.ops).json()
    # HSE limité au site S2 : l'incident du site S1 est indiscernable d'un identifiant inexistant.
    for headers in (w.hse_s2.headers, w.other_hse.headers):
        assert client.get(f"{API}/hse/incidents/{iid}", headers=headers).status_code == 404
        listed = client.get(f"{API}/hse/incidents", headers=headers).json()
        assert iid not in {i["hse_incident_id"] for i in listed["items"]}
        actions = client.get(f"{API}/hse/corrective-actions", headers=headers).json()
        assert action["hse_corrective_action_id"] not in {
            a["hse_corrective_action_id"] for a in actions["items"]
        }
        forged = _action_post(client, action, "decision", headers, action="CANCEL", reason_code="OTHER")
        assert forged.status_code == 404
        moved = client.post(
            f"{API}/hse/incidents/{iid}/transition",
            headers={**headers, "If-Match": '"1"'},
            json={"action": "START_INVESTIGATION"},
        )
        assert moved.status_code == 404
    s2_filter = client.get(
        f"{API}/hse/incidents", headers=w.hse_s2.headers, params={"site_id": str(w.t.sites["S1"])}
    )
    assert s2_filter.status_code == 404
    foreign_site = client.post(
        f"{API}/hse/incidents",
        headers=w.other_hse.headers,
        json={
            "site_id": str(w.t.sites["S1"]),
            "category": "OTHER",
            "severity": "LOW",
            "title": "Tentative inter-tenant",
            "description": "Site d'un autre tenant référencé.",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    assert foreign_site.status_code == 422 and foreign_site.json()["code"] == "REFERENCE_NOT_FOUND"
    assert client.get(f"{API}/hse/incidents/{uuid.uuid4()}", headers=w.hse.headers).status_code == 404


def test_summary_counts(client: TestClient, w: World, api: Api) -> None:
    t = api.tenant()
    hse = api.user(t, "HSE")
    ops = api.user(t, "OPS_MANAGER")
    base = {
        "site_id": str(t.sites["S1"]),
        "title": "Événement fictif",
        "description": "Description fictive suffisante.",
        "occurred_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
    }
    for category, severity, injured, lost in (
        ("INJURY", "HIGH", 1, True),
        ("NEAR_MISS", "LOW", 0, False),
        ("SPILL", "MEDIUM", 0, False),
    ):
        resp = client.post(
            f"{API}/hse/incidents",
            headers=ops.headers,
            json={
                **base,
                "category": category,
                "severity": severity,
                "injured_count": injured,
                "lost_time": lost,
            },
        )
        assert resp.status_code == 201, resp.text
    summary = client.get(f"{API}/hse/summary", headers=hse.headers).json()
    assert summary["incidents"] == 3 and summary["injured"] == 1 and summary["lost_time_incidents"] == 1
    assert summary["by_severity"] == {"HIGH": 1, "LOW": 1, "MEDIUM": 1}
    assert summary["open_incidents"] == 3 and summary["overdue_actions"] == 0


def test_events_are_append_only_and_rls_enforced(client: TestClient, w: World) -> None:
    iid = _report(client, w).json()["hse_incident_id"]
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            with pytest.raises(DBAPIError) as refused:
                conn.execute(
                    text("UPDATE hse_incident_event SET reason = 'x' WHERE hse_incident_id = :i"), {"i": iid}
                )
            assert getattr(refused.value.orig, "sqlstate", None) in ("MF001", "42501")
            conn.rollback()
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.other.tenant_id)})
            hidden = conn.execute(
                text("SELECT count(*) FROM hse_incident WHERE hse_incident_id = :i"), {"i": iid}
            ).scalar()
            assert hidden == 0
            conn.rollback()
    finally:
        engine.dispose()


# --- Rejeu hors ligne (outbox terrain, Idempotency-Key) -------------------------------------------------


def _offline_body(w: World, **extra: object) -> dict[str, object]:
    return {
        "site_id": str(w.t.sites["S1"]),
        "category": "SPILL",
        "severity": "LOW",
        "title": "Fuite saisie hors ligne",
        "description": "Flaque d'huile constatée sans réseau sur la piste.",
        "occurred_at": (datetime.now(UTC) - timedelta(hours=5)).isoformat(),
        **extra,
    }


def _replay(client: TestClient, headers: dict[str, str], key: str, body: dict[str, object]):  # type: ignore[no-untyped-def]
    return client.post(f"{API}/hse/incidents", headers={**headers, "Idempotency-Key": key}, json=body)


def test_offline_replay_creates_the_incident_once(client: TestClient, w: World) -> None:
    key = str(uuid.uuid4())
    body = _offline_body(w)
    first = _replay(client, w.dispatcher.headers, key, body)
    assert first.status_code == 201, first.text
    assert "Idempotency-Replayed" not in first.headers
    again = _replay(client, w.dispatcher.headers, key, body)
    assert again.status_code == 201 and again.headers["Idempotency-Replayed"] == "true"
    assert again.json()["hse_incident_id"] == first.json()["hse_incident_id"]
    assert again.json()["reference"] == first.json()["reference"]
    listed = client.get(f"{API}/hse/incidents", headers=w.hse.headers, params={"page_size": 200}).json()
    assert sum(1 for i in listed["items"] if i["title"] == "Fuite saisie hors ligne") == 1
    altered = _replay(client, w.dispatcher.headers, key, {**body, "severity": "HIGH"})
    assert altered.status_code == 422 and altered.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    events = client.get(
        f"{API}/hse/incidents/{first.json()['hse_incident_id']}", headers=w.hse.headers
    ).json()
    assert [e["event_type"] for e in events["events"]] == ["REPORTED"]


def test_offline_key_is_bound_to_the_account(client: TestClient, w: World) -> None:
    key = str(uuid.uuid4())
    body = _offline_body(w, title="Clé partagée entre comptes")
    mine = _replay(client, w.dispatcher.headers, key, body).json()
    # Le même identifiant d'opération sous un autre compte ne rejoue pas l'incident d'autrui.
    theirs = _replay(client, w.ops.headers, key, body)
    assert theirs.status_code == 201 and "Idempotency-Replayed" not in theirs.headers
    assert theirs.json()["hse_incident_id"] != mine["hse_incident_id"]
    assert theirs.json()["reported_by"] == str(w.ops.user_id)
    foreign = _replay(client, w.other_hse.headers, key, body)
    assert foreign.status_code == 422 and foreign.json()["code"] == "REFERENCE_NOT_FOUND"


def test_offline_replay_rechecks_authorization_and_rolls_back(client: TestClient, w: World, api: Api) -> None:
    reporter = api.user(w.t, "DISPATCHER", "SITE", "S1")
    # Un échec métier annule aussi la réservation de clé : pas de clé bloquée « en cours ».
    key = str(uuid.uuid4())
    invalid = _offline_body(w, vehicle_id=w.vehicle_s2)
    assert _replay(client, reporter.headers, key, invalid).status_code == 422
    assert _replay(client, reporter.headers, key, invalid).json()["code"] == "REFERENCE_NOT_FOUND"
    # Rôle retiré entre la saisie hors ligne et la synchronisation : refus, rien n'est créé.
    pending_key = str(uuid.uuid4())
    assignment = client.get(
        f"{API}/role-assignments", headers=w.t.admin.headers, params={"user_id": str(reporter.user_id)}
    ).json()["items"][0]
    revoked = client.post(
        f"{API}/role-assignments/{assignment['user_role_assignment_id']}/revoke",
        headers={**w.t.admin.headers, "If-Match": f'"{assignment["row_version"]}"'},
    )
    assert revoked.status_code == 200, revoked.text
    late = _replay(client, reporter.headers, pending_key, _offline_body(w, title="Saisie après retrait"))
    assert late.status_code in (401, 403)
    listed = client.get(f"{API}/hse/incidents", headers=w.hse.headers, params={"page_size": 200}).json()
    assert all(i["title"] != "Saisie après retrait" for i in listed["items"])


def test_offline_replay_rejects_malformed_key(client: TestClient, w: World) -> None:
    bad = _replay(client, w.dispatcher.headers, "cle invalide!", _offline_body(w))
    assert bad.status_code == 422
