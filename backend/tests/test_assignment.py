"""Tranche 1c — US-1.22 à US-1.25, D-27 (prise de poste), D-30 (suspension), D-11/D-13 (blocages)."""

import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.clock import SystemClock
from app.core.config import get_settings
from tests.conftest import API, Account, Api, TenantFixture

FAR = (datetime.now(UTC) + timedelta(days=3650)).date().isoformat()


class OffsetClock:
    """Horloge décalée (reste dans la durée de vie du jeton d'accès)."""

    def __init__(self, offset: timedelta) -> None:
        self.offset = offset

    def now(self) -> datetime:
        return SystemClock().now() + self.offset


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(instant: datetime) -> str:
    return instant.isoformat()


@dataclass
class World:
    t: TenantFixture
    ops: Account
    hr: Account
    dispatcher: Account  # portée SITE S1
    categories: dict[str, str]


@pytest.fixture
def w(api: Api, client: TestClient) -> World:
    t = api.tenant()
    cats = client.get(f"{API}/vehicle-categories", headers=t.admin.headers).json()
    return World(
        t,
        api.user(t, "OPS_MANAGER"),
        api.user(t, "HR"),
        api.user(t, "DISPATCHER", "SITE", "S1"),
        {c["code"]: c["vehicle_category_id"] for c in cats},
    )


def _vehicle(client: TestClient, w: World, site: str = "S1", category: str = "RIGID_DUMP_TRUCK") -> str:
    resp = client.post(
        f"{API}/vehicles",
        headers=w.t.admin.headers,
        json={
            "site_id": str(w.t.sites[site]),
            "vehicle_category_id": w.categories[category],
            "fleet_number": f"P-{uuid.uuid4().hex[:6]}",
        },
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["vehicle_id"])


def _driver(
    client: TestClient,
    w: World,
    site: str = "S1",
    *,
    license_category: str | None = "C",
    license_expiry: str = FAR,
    authorization: str | None = "RIGID_DUMP_TRUCK",
    authorization_to: str | None = None,
) -> str:
    resp = client.post(
        f"{API}/drivers",
        headers=w.hr.headers,
        json={
            "site_id": str(w.t.sites[site]),
            "employee_number": f"M-{uuid.uuid4().hex[:6]}",
            "last_name": "Nom-Test",
            "first_name": "Prénom",
        },
    )
    assert resp.status_code == 201, resp.text
    driver_id = str(resp.json()["driver_id"])
    if license_category:
        lic = client.post(
            f"{API}/drivers/{driver_id}/licenses",
            headers=w.hr.headers,
            json={
                "license_number": f"PERMIS-{uuid.uuid4().hex[:6]}",
                "category_code": license_category,
                "issue_date": "2015-01-01",
                "expiry_date": license_expiry,
            },
        )
        assert lic.status_code == 201, lic.text
    if authorization:
        body: dict[str, object] = {
            "qualification_type": "DRIVING_AUTHORIZATION",
            "vehicle_category_id": w.categories[authorization],
            "valid_from": "2020-01-01",
        }
        if authorization_to:
            body["valid_to"] = authorization_to
        q = client.post(f"{API}/drivers/{driver_id}/qualifications", headers=w.hr.headers, json=body)
        assert q.status_code == 201, q.text
    return driver_id


def _create(  # type: ignore[no-untyped-def]
    client: TestClient,
    w: World,
    vehicle: str,
    driver: str,
    start: datetime | None = None,
    end: datetime | None = None,
    headers: dict[str, str] | None = None,
):
    body: dict[str, object] = {
        "vehicle_id": vehicle,
        "driver_id": driver,
        "valid_from": _iso(start or _now()),
    }
    if end is not None:
        body["valid_to"] = _iso(end)
    return client.post(f"{API}/vehicle-assignments", headers=headers or w.ops.headers, json=body)


def _action(  # type: ignore[no-untyped-def]
    client: TestClient,
    w: World,
    assignment_id: str,
    action: str,
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
):
    url = f"{API}/vehicle-assignments/{assignment_id}"
    auth = headers or w.ops.headers
    version = client.get(url, headers=auth).headers["ETag"]
    return client.post(f"{url}/{action}", headers={**auth, "If-Match": version}, json=body)


def _reasons(resp) -> list[str]:  # type: ignore[no-untyped-def]
    assert resp.status_code == 422 and resp.json()["code"] == "ASSIGNMENT_NOT_ELIGIBLE", resp.text
    return [r["code"] for r in resp.json()["details"]["reasons"]]


# --- US-1.22 Création ---------------------------------------------------------------------------------


def test_us122_a1_create_active_or_planned_audited_and_compliant(client: TestClient, w: World) -> None:
    vehicle, driver = _vehicle(client, w), _driver(client, w)
    resp = _create(client, w, vehicle, driver, end=_now() + timedelta(hours=8))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "ACTIVE" and body["compliance"]["status"] == "COMPLIANT"
    assert body["vehicle_id"] == vehicle and body["driver_display_name"] == "NOM-TEST Prénom"
    assert resp.headers["ETag"] == '"1"'
    events = client.get(
        f"{API}/audit-events",
        headers=w.t.admin.headers,
        params={"action": "vehicle_assignment.create"},
    ).json()["items"]
    assert len(events) == 1 and events[0]["after_data"]["driver_id"] == driver
    assert "Nom-Test" not in str(events[0])  # jamais de nom dans le journal (D-10)

    other_vehicle, other_driver = _vehicle(client, w), _driver(client, w)
    planned = _create(client, w, other_vehicle, other_driver, start=_now() + timedelta(days=1))
    assert planned.status_code == 201 and planned.json()["status"] == "PLANNED"
    assert "compliance" not in planned.json()  # US-1.25 A6
    assert planned.json()["warnings"] == [{"code": "NEXT_EXPIRY", "date": FAR}]


def test_us122_a2_a3_a13_overlaps_vehicle_then_driver(client: TestClient, w: World) -> None:
    vehicle, driver = _vehicle(client, w), _driver(client, w)
    start = _now() + timedelta(hours=1)
    assert _create(client, w, vehicle, driver, start, start + timedelta(hours=8)).status_code == 201
    again = _create(client, w, vehicle, driver, start, start + timedelta(hours=8))  # double clic (A13)
    assert (again.status_code, again.json()["code"]) == (409, "VEHICLE_ASSIGNMENT_OVERLAP")
    same_driver = _create(client, w, _vehicle(client, w), driver, start + timedelta(hours=2))
    assert (same_driver.status_code, same_driver.json()["code"]) == (409, "DRIVER_ASSIGNMENT_OVERLAP")
    # Intervalle semi-ouvert : commencer exactement à la fin est accepté (RM-034).
    contiguous = _create(client, w, vehicle, _driver(client, w), start + timedelta(hours=8))
    assert contiguous.status_code == 201, contiguous.text
    listed = client.get(
        f"{API}/vehicle-assignments", headers=w.ops.headers, params={"vehicle_id": vehicle}
    ).json()
    assert listed["total"] == 2


def test_us122_a4_concurrent_creations_exactly_one_wins(client: TestClient, w: World) -> None:
    vehicle = _vehicle(client, w)
    drivers = [_driver(client, w), _driver(client, w)]
    start = _now() + timedelta(hours=2)
    barrier = threading.Barrier(2)
    results: list[tuple[int, str | None]] = []

    def run(driver: str) -> None:
        barrier.wait(timeout=10)
        resp = _create(client, w, vehicle, driver, start, start + timedelta(hours=4))
        results.append((resp.status_code, resp.json().get("code")))

    threads = [threading.Thread(target=run, args=(d,)) for d in drivers]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert sorted(results, key=lambda r: r[0]) == [(201, None), (409, "VEHICLE_ASSIGNMENT_OVERLAP")]


def test_us122_a5_a6_a8_a11_all_reasons_listed(client: TestClient, w: World) -> None:
    """D-29 : un seul code, tous les motifs (site, antidatage, statuts)."""
    vehicle = _vehicle(client, w)
    url = f"{API}/vehicles/{vehicle}"
    etag = client.get(url, headers=w.t.admin.headers).headers["ETag"]
    immobilized = client.post(
        f"{url}/status",
        headers={**w.t.admin.headers, "If-Match": etag},
        json={"status": "IMMOBILIZED", "reason_code": "BREAKDOWN"},
    )
    assert immobilized.status_code == 200
    driver = _driver(client, w, site="S2")
    durl = f"{API}/drivers/{driver}"
    suspended = client.post(
        f"{durl}/status",
        headers={**w.hr.headers, "If-Match": client.get(durl, headers=w.hr.headers).headers["ETag"]},
        json={"status": "SUSPENDED", "suspension_reason_code": "INVESTIGATION"},
    )
    assert suspended.status_code == 200
    resp = _create(client, w, vehicle, driver, start=_now() - timedelta(hours=2))
    assert set(_reasons(resp)) >= {
        "ASSIGNMENT_SITE_MISMATCH",
        "ASSIGNMENT_BACKDATED",
        "DRIVER_NOT_ACTIVE",
        "VEHICLE_NOT_AVAILABLE",
    }


def test_us122_a7_license_and_qualification_reasons(client: TestClient, w: World) -> None:
    vehicle = _vehicle(client, w)
    no_license = _driver(client, w, license_category=None)
    assert "DRIVER_LICENSE_MISSING" in _reasons(_create(client, w, vehicle, no_license))
    wrong_category = _driver(client, w, license_category="B")
    assert "DRIVER_LICENSE_CATEGORY_MISSING" in _reasons(_create(client, w, vehicle, wrong_category))
    yesterday = (_now() - timedelta(days=1)).date().isoformat()
    expired = _driver(client, w, license_expiry=yesterday)
    resp = _create(client, w, vehicle, expired)
    assert _reasons(resp) == ["DRIVER_LICENSE_EXPIRED"]
    assert resp.json()["details"]["reasons"][0]["date"] == yesterday
    assert "PERMIS-" not in resp.text  # jamais le numéro de permis (A7)
    soon = (_now() + timedelta(days=10)).date().isoformat()
    short = _driver(client, w, license_expiry=soon)
    too_long = _create(client, w, vehicle, short, end=_now() + timedelta(days=20))
    assert _reasons(too_long) == ["DRIVER_LICENSE_EXPIRES_BEFORE_END"]
    no_authorization = _driver(client, w, authorization=None)
    assert _reasons(_create(client, w, vehicle, no_authorization)) == ["DRIVER_QUALIFICATION_MISSING"]
    other_category = _driver(client, w, authorization="WHEEL_LOADER")
    assert _reasons(_create(client, w, vehicle, other_category)) == ["DRIVER_QUALIFICATION_MISSING"]


def test_us122_expiring_license_is_accepted_with_warning(client: TestClient, w: World) -> None:
    soon = (_now() + timedelta(days=10)).date().isoformat()
    resp = _create(client, w, _vehicle(client, w), _driver(client, w, license_expiry=soon))
    assert resp.status_code == 201, resp.text
    codes = {x["code"] for x in resp.json()["warnings"]}
    assert codes == {"LICENSE_EXPIRING", "NEXT_EXPIRY"}
    assert resp.json()["compliance"]["warnings"] == [{"code": "LICENSE_EXPIRING", "date": soon}]


def test_us122_category_without_license_requirement(client: TestClient, w: World) -> None:
    """BULLDOZER : aucun permis d'État au catalogue fictif (C-07), habilitation interne exigée."""
    vehicle = _vehicle(client, w, category="BULLDOZER")
    driver = _driver(client, w, license_category=None, authorization="BULLDOZER")
    assert _create(client, w, vehicle, driver).status_code == 201


def test_us122_a9_a10_references_and_interval(client: TestClient, w: World, api: Api) -> None:
    vehicle, driver = _vehicle(client, w), _driver(client, w)
    start = _now() + timedelta(hours=1)
    inverted = _create(client, w, vehicle, driver, start, start)
    assert (inverted.status_code, inverted.json()["code"]) == (422, "END_BEFORE_START")
    naive = client.post(
        f"{API}/vehicle-assignments",
        headers=w.ops.headers,
        json={"vehicle_id": vehicle, "driver_id": driver, "valid_from": "2030-01-01T08:00:00"},
    )
    assert naive.status_code == 422  # fuseau obligatoire (A14)
    other = api.tenant()
    foreign_ops = api.user(other, "OPS_MANAGER")
    foreign = _create(client, w, vehicle, driver, headers=foreign_ops.headers)
    assert (foreign.status_code, foreign.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    out_of_scope = _create(client, w, _vehicle(client, w, "S2"), driver, headers=w.dispatcher.headers)
    assert (out_of_scope.status_code, out_of_scope.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    assert out_of_scope.json()["details"] == [{"field": "vehicle_id"}]


def test_us122_a12_forbidden_roles(client: TestClient, w: World, api: Api) -> None:
    vehicle, driver = _vehicle(client, w), _driver(client, w)
    for headers in (w.hr.headers, w.t.admin.headers, api.user(w.t, "HSE").headers):
        resp = _create(client, w, vehicle, driver, headers=headers)
        assert (resp.status_code, resp.json()["code"]) == (403, "PERMISSION_DENIED")
    assert _create(client, w, vehicle, driver, headers=w.dispatcher.headers).status_code == 201


def test_us122_a14_site_timezone_offset_stored_utc(client: TestClient, w: World) -> None:
    vehicle, driver = _vehicle(client, w), _driver(client, w)
    local = (_now() + timedelta(days=2)).astimezone(UTC).replace(microsecond=0)
    lagos = local.astimezone(ZoneInfo("Africa/Lagos"))  # UTC+1
    resp = _create(client, w, vehicle, driver, start=lagos)
    assert resp.status_code == 201
    stored = datetime.fromisoformat(resp.json()["valid_from"])
    assert stored == local and stored.utcoffset() == timedelta(0)


# --- US-1.23 Clôture et annulation --------------------------------------------------------------------


def test_us123_complete_cancel_and_state_rules(client: TestClient, w: World) -> None:
    vehicle, driver = _vehicle(client, w), _driver(client, w)
    active = _create(client, w, vehicle, driver, start=_now() - timedelta(minutes=5)).json()
    future = _action(
        client,
        w,
        active["vehicle_assignment_id"],
        "complete",
        {"ended_at": _iso(_now() + timedelta(hours=1))},
    )
    assert (future.status_code, future.json()["code"]) == (422, "END_IN_FUTURE")
    early = _action(
        client,
        w,
        active["vehicle_assignment_id"],
        "complete",
        {"ended_at": _iso(_now() - timedelta(hours=1))},
    )
    assert (early.status_code, early.json()["code"]) == (422, "END_BEFORE_START")
    wrong = _action(client, w, active["vehicle_assignment_id"], "cancel", {"reason_code": "PLAN_CHANGED"})
    assert (wrong.status_code, wrong.json()["code"]) == (409, "ASSIGNMENT_STATE_INVALID")
    done = _action(client, w, active["vehicle_assignment_id"], "complete", {})
    assert done.status_code == 200 and done.json()["status"] == "COMPLETED"
    assert done.json()["valid_to"] is not None and done.json()["status_reason"] == "END_OF_SHIFT"
    again = _action(client, w, active["vehicle_assignment_id"], "complete", {})
    assert (again.status_code, again.json()["code"]) == (409, "ASSIGNMENT_STATE_INVALID")
    # A8 : une nouvelle affectation peut commencer à l'instant de clôture.
    ended = datetime.fromisoformat(done.json()["valid_to"])
    assert _create(client, w, vehicle, _driver(client, w), start=ended).status_code == 201

    planned = _create(
        client, w, _vehicle(client, w), _driver(client, w), start=_now() + timedelta(days=1)
    ).json()
    no_reason = _action(client, w, planned["vehicle_assignment_id"], "cancel", {})
    assert no_reason.status_code == 422
    not_started = _action(client, w, planned["vehicle_assignment_id"], "complete", {})
    assert (not_started.status_code, not_started.json()["code"]) == (409, "ASSIGNMENT_STATE_INVALID")
    cancelled = _action(
        client, w, planned["vehicle_assignment_id"], "cancel", {"reason_code": "PLAN_CHANGED"}
    )
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    # Ressources libérées : le même créneau redevient disponible.
    redo = _create(
        client,
        w,
        planned["vehicle_id"],
        planned["driver_id"],
        start=datetime.fromisoformat(planned["valid_from"]),
    )
    assert redo.status_code == 201, redo.text


def test_us123_a9_stale_version_and_if_match_required(client: TestClient, w: World) -> None:
    created = _create(client, w, _vehicle(client, w), _driver(client, w)).json()
    url = f"{API}/vehicle-assignments/{created['vehicle_assignment_id']}"
    missing = client.post(f"{url}/complete", headers=w.ops.headers, json={})
    assert (missing.status_code, missing.json()["code"]) == (422, "IF_MATCH_REQUIRED")
    stale = client.post(f"{url}/complete", headers={**w.ops.headers, "If-Match": '"99"'}, json={})
    assert (stale.status_code, stale.json()["code"]) == (409, "VERSION_CONFLICT")


# --- D-27 / D-30 Prise de poste, suspension, reprise --------------------------------------------------


def test_d27_activation_rechecks_eligibility(
    client: TestClient, w: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    planned = _create(
        client, w, _vehicle(client, w), _driver(client, w), start=_now() + timedelta(minutes=10)
    ).json()
    aid = planned["vehicle_assignment_id"]
    too_early = _action(client, w, aid, "activate")
    assert (too_early.status_code, too_early.json()["details"]["reason"]) == (409, "NOT_YET_STARTED")
    monkeypatch.setattr(client.app.state, "clock", OffsetClock(timedelta(minutes=11)))  # type: ignore[attr-defined]
    overdue = client.get(f"{API}/vehicle-assignments/{aid}", headers=w.ops.headers).json()
    assert overdue["activation_overdue"] is True
    # Passer le conducteur en indisponible est refusé tant que l'affectation est ouverte (D-11).
    durl = f"{API}/drivers/{planned['driver_id']}"
    blocked = client.post(
        f"{durl}/status",
        headers={**w.hr.headers, "If-Match": client.get(durl, headers=w.hr.headers).headers["ETag"]},
        json={"status": "UNAVAILABLE", "unavailability_reason": "LEAVE"},
    )
    assert (blocked.status_code, blocked.json()["code"]) == (409, "OPEN_ASSIGNMENTS_EXIST")
    # Permis retiré entre la planification et la prise de poste : activation refusée (RM-031).
    lic = client.get(f"{durl}/licenses", headers=w.hr.headers).json()[0]
    lurl = f"{API}/driver-licenses/{lic['driver_license_id']}"
    withdrawn = client.patch(
        lurl, headers={**w.hr.headers, "If-Match": f'"{lic["row_version"]}"'}, json={"status": "WITHDRAWN"}
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert _reasons(_action(client, w, aid, "activate")) == ["DRIVER_LICENSE_EXPIRED"]
    restored = client.patch(
        lurl, headers={**w.hr.headers, "If-Match": withdrawn.headers["ETag"]}, json={"status": "VALID"}
    )
    assert restored.status_code == 200, restored.text
    activated = _action(client, w, aid, "activate", headers=w.dispatcher.headers)
    assert activated.status_code == 200 and activated.json()["status"] == "ACTIVE"
    assert activated.json()["activation_overdue"] is False


def test_d30_suspend_and_resume(client: TestClient, w: World) -> None:
    created = _create(client, w, _vehicle(client, w), _driver(client, w)).json()
    aid = created["vehicle_assignment_id"]
    no_reason = _action(client, w, aid, "suspend", {})
    assert no_reason.status_code == 422
    suspended = _action(client, w, aid, "suspend", {"reason_code": "WEATHER"})
    assert suspended.status_code == 200 and suspended.json()["status"] == "SUSPENDED"
    assert "compliance" not in suspended.json()
    # Le créneau reste occupé (D-30).
    busy = _create(client, w, created["vehicle_id"], _driver(client, w))
    assert busy.json()["code"] == "VEHICLE_ASSIGNMENT_OVERLAP"
    resumed = _action(client, w, aid, "resume")
    assert resumed.status_code == 200 and resumed.json()["status"] == "ACTIVE"
    assert resumed.json()["status_reason"] is None
    events = client.get(f"{API}/audit-events", headers=w.t.admin.headers, params={"entity_id": aid}).json()[
        "items"
    ]
    assert {e["action"] for e in events} >= {
        "vehicle_assignment.create",
        "vehicle_assignment.suspend",
        "vehicle_assignment.resume",
    }


# --- D-11 / D-13 Blocages de statut et de site --------------------------------------------------------


def test_d11_d13_open_assignment_blocks_status_and_site_changes(client: TestClient, w: World) -> None:
    created = _create(client, w, _vehicle(client, w), _driver(client, w)).json()
    vurl = f"{API}/vehicles/{created['vehicle_id']}"

    def vehicle_headers() -> dict[str, str]:
        return {**w.ops.headers, "If-Match": client.get(vurl, headers=w.ops.headers).headers["ETag"]}

    for resp in (
        client.post(f"{vurl}/status", headers=vehicle_headers(), json={"status": "IN_MAINTENANCE"}),
        client.post(f"{vurl}/retire", headers=vehicle_headers(), json={"reason_code": "SOLD"}),
        client.patch(vurl, headers=vehicle_headers(), json={"site_id": str(w.t.sites["S2"])}),
    ):
        assert (resp.status_code, resp.json()["code"]) == (409, "OPEN_ASSIGNMENTS_EXIST")
        assert resp.json()["details"]["items"][0]["vehicle_assignment_id"] == created["vehicle_assignment_id"]
    durl = f"{API}/drivers/{created['driver_id']}"
    moved = client.patch(
        durl,
        headers={**w.hr.headers, "If-Match": client.get(durl, headers=w.hr.headers).headers["ETag"]},
        json={"site_id": str(w.t.sites["S2"])},
    )
    assert (moved.status_code, moved.json()["code"]) == (409, "OPEN_ASSIGNMENTS_EXIST")
    assert _action(client, w, created["vehicle_assignment_id"], "complete", {}).status_code == 200
    freed = client.post(f"{vurl}/status", headers=vehicle_headers(), json={"status": "IN_MAINTENANCE"})
    assert freed.status_code == 200


# --- US-1.24 / US-1.25 Lecture, historique, conformité ------------------------------------------------


def test_us124_history_at_instant_and_scope(client: TestClient, w: World, api: Api) -> None:
    vehicle = _vehicle(client, w)
    start = _now() + timedelta(days=1)
    first = _create(client, w, vehicle, _driver(client, w), start, start + timedelta(hours=8)).json()
    second = _create(client, w, vehicle, _driver(client, w), start + timedelta(hours=8)).json()
    history = client.get(f"{API}/vehicles/{vehicle}/assignments", headers=w.ops.headers).json()
    assert [a["vehicle_assignment_id"] for a in history["items"]] == [
        second["vehicle_assignment_id"],
        first["vehicle_assignment_id"],
    ]

    def at(instant: datetime) -> list[str]:
        items = client.get(
            f"{API}/vehicle-assignments",
            headers=w.ops.headers,
            params={"vehicle_id": vehicle, "at": _iso(instant)},
        ).json()["items"]
        return [a["vehicle_assignment_id"] for a in items]

    assert at(start) == [first["vehicle_assignment_id"]]  # début inclus
    assert at(start + timedelta(hours=8)) == [second["vehicle_assignment_id"]]  # fin exclue
    assert at(start - timedelta(seconds=1)) == []
    driver_history = client.get(f"{API}/drivers/{first['driver_id']}/assignments", headers=w.hr.headers)
    assert driver_history.json()["total"] == 1

    s2 = _create(client, w, _vehicle(client, w, "S2"), _driver(client, w, "S2")).json()
    visible = client.get(f"{API}/vehicle-assignments", headers=w.dispatcher.headers).json()["items"]
    assert s2["vehicle_assignment_id"] not in {a["vehicle_assignment_id"] for a in visible}
    hidden = client.get(
        f"{API}/vehicle-assignments/{s2['vehicle_assignment_id']}", headers=w.dispatcher.headers
    )
    assert hidden.status_code == 404
    assert (
        client.get(f"{API}/vehicles/{s2['vehicle_id']}/assignments", headers=w.dispatcher.headers).status_code
        == 404
    )
    for role in ("FINANCE", "DRIVER"):
        account = api.user(w.t, role, "SITE", "S1")
        assert client.get(f"{API}/vehicle-assignments", headers=account.headers).status_code == 403
    assert client.get(f"{API}/vehicle-assignments", headers=w.t.admin.headers).status_code == 403


def test_us125_non_compliance_derived_on_read(client: TestClient, w: World) -> None:
    created = _create(client, w, _vehicle(client, w), _driver(client, w)).json()
    aid = created["vehicle_assignment_id"]
    licenses = client.get(f"{API}/drivers/{created['driver_id']}/licenses", headers=w.hr.headers).json()
    lurl = f"{API}/driver-licenses/{licenses[0]['driver_license_id']}"
    withdrawn = client.patch(
        lurl,
        headers={**w.hr.headers, "If-Match": f'"{licenses[0]["row_version"]}"'},
        json={"status": "WITHDRAWN", "status_note": "Retrait fictif"},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    read = client.get(f"{API}/vehicle-assignments/{aid}", headers=w.ops.headers).json()
    assert read["status"] == "ACTIVE"  # aucune transition automatique (D-12)
    assert read["compliance"]["status"] == "NON_COMPLIANT"
    assert [r["code"] for r in read["compliance"]["reasons"]] == ["LICENSE_EXPIRED"]
    filtered = client.get(
        f"{API}/vehicle-assignments", headers=w.ops.headers, params={"compliance": "NON_COMPLIANT"}
    ).json()
    assert [a["vehicle_assignment_id"] for a in filtered["items"]] == [aid] and filtered["total"] == 1
    compliant = client.get(
        f"{API}/vehicle-assignments", headers=w.ops.headers, params={"compliance": "COMPLIANT"}
    ).json()
    assert compliant["total"] == 0
    # Une affectation non conforme reste clôturable (A3).
    assert _action(client, w, aid, "complete", {"reason_code": "NON_COMPLIANCE"}).status_code == 200


# --- Garanties en base (A4, A9, RM-040, RM-042) -------------------------------------------------------


@pytest.fixture(scope="module")
def app_engine() -> Iterator[Engine]:
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    yield engine
    engine.dispose()


def _raw_insert(conn, w: World, vehicle: str, driver: str, site: str, start: datetime) -> None:  # type: ignore[no-untyped-def]
    conn.execute(
        text(
            "INSERT INTO vehicle_assignment (tenant_id, site_id, vehicle_id, driver_id, valid_from,"
            " eligibility_snapshot, created_by) VALUES (:t, :s, :v, :d, :f, '{}'::jsonb, :u)"
        ),
        {
            "t": str(w.t.tenant_id),
            "s": str(w.t.sites[site]),
            "v": vehicle,
            "d": driver,
            "f": start,
            "u": str(w.ops.user_id),
        },
    )


def test_db_guards_overlap_site_and_immutability(client: TestClient, w: World, app_engine: Engine) -> None:
    created = _create(client, w, _vehicle(client, w), _driver(client, w)).json()
    with app_engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
        with pytest.raises(IntegrityError) as overlap:
            _raw_insert(conn, w, created["vehicle_id"], _driver(client, w), "S1", _now() + timedelta(hours=1))
        assert "ex_va_vehicle_no_overlap" in str(overlap.value)
        conn.rollback()
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
        with pytest.raises(DBAPIError) as mismatch:
            _raw_insert(conn, w, _vehicle(client, w), _driver(client, w, "S2"), "S1", _now())
        assert getattr(mismatch.value.orig, "sqlstate", None) == "MF004"
        conn.rollback()
    assert _action(client, w, created["vehicle_assignment_id"], "complete", {}).status_code == 200
    with app_engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
        with pytest.raises(DBAPIError) as immutable:
            conn.execute(
                text("UPDATE vehicle_assignment SET shift_code = 'X' WHERE vehicle_assignment_id = :a"),
                {"a": created["vehicle_assignment_id"]},
            )
        assert getattr(immutable.value.orig, "sqlstate", None) == "MF003"
        conn.rollback()
        # Sans contexte tenant : aucune ligne visible (RLS forcée).
        assert conn.execute(text("SELECT count(*) FROM vehicle_assignment")).scalar_one() == 0


# --- SEC1C-05 / SEC1C-06 Divulgation limitée aux droits de lecture ------------------------------------


def test_sec1c05_blocker_list_only_for_assignment_readers(client: TestClient, w: World) -> None:
    """TENANT_ADMIN change le statut d'un véhicule sans lire les affectations (D-10) : total seulement."""
    created = _create(client, w, _vehicle(client, w), _driver(client, w)).json()
    vurl = f"{API}/vehicles/{created['vehicle_id']}"
    for headers, has_items in ((w.t.admin.headers, False), (w.ops.headers, True)):
        etag = client.get(vurl, headers=headers).headers["ETag"]
        resp = client.post(
            f"{vurl}/status", headers={**headers, "If-Match": etag}, json={"status": "IN_MAINTENANCE"}
        )
        assert (resp.status_code, resp.json()["code"]) == (409, "OPEN_ASSIGNMENTS_EXIST")
        assert resp.json()["details"]["total"] == 1
        assert ("items" in resp.json()["details"]) is has_items


def test_sec1c06_document_reasons_hidden_without_document_read(
    client: TestClient, w: World, api: Api
) -> None:
    created = _create(client, w, _vehicle(client, w), _driver(client, w)).json()
    lic = client.get(f"{API}/drivers/{created['driver_id']}/licenses", headers=w.hr.headers).json()[0]
    withdrawn = client.patch(
        f"{API}/driver-licenses/{lic['driver_license_id']}",
        headers={**w.hr.headers, "If-Match": f'"{lic["row_version"]}"'},
        json={"status": "WITHDRAWN"},
    )
    assert withdrawn.status_code == 200
    url = f"{API}/vehicle-assignments/{created['vehicle_assignment_id']}"
    fuel = api.user(w.t, "FUEL_MANAGER", "SITE", "S1")
    direction = api.user(w.t, "DIRECTION")
    hse = api.user(w.t, "HSE")
    for account, reasons in ((fuel, []), (direction, []), (hse, ["LICENSE_EXPIRED"])):
        compliance = client.get(url, headers=account.headers).json()["compliance"]
        assert compliance["status"] == "NON_COMPLIANT"
        assert [r["code"] for r in compliance["reasons"]] == reasons


# --- Revue indépendante (SEC1C-R-01, R-03, R-06, R-11, SEC1C-03) --------------------------------------


def test_sec1c_r01_retroactive_end_is_bounded(client: TestClient, w: World) -> None:
    created = _create(
        client, w, _vehicle(client, w), _driver(client, w), start=_now() - timedelta(minutes=10)
    )
    aid = created.json()["vehicle_assignment_id"]
    # Effacer les heures conduites (fin = début + 1 s) est refusé au-delà de la tolérance d'antidatage.
    ended = datetime.fromisoformat(created.json()["valid_from"]) + timedelta(seconds=1)
    settings = get_settings()
    original = settings.assignment_backdate_tolerance
    settings.assignment_backdate_tolerance = timedelta(minutes=1)
    try:
        refused = _action(client, w, aid, "complete", {"ended_at": _iso(ended)})
    finally:
        settings.assignment_backdate_tolerance = original
    assert (refused.status_code, refused.json()["code"]) == (422, "END_BACKDATED")
    assert _action(client, w, aid, "complete", {}).status_code == 200


def test_sec1c_r01_overdue_assignment_closes_at_planned_end(
    client: TestClient, w: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    start = _now() + timedelta(minutes=10)  # au-delà de la tolérance d'horloge : PLANNED
    created = _create(client, w, _vehicle(client, w), _driver(client, w), start, start + timedelta(minutes=2))
    planned_end = created.json()["valid_to"]
    aid = created.json()["vehicle_assignment_id"]
    monkeypatch.setattr(client.app.state, "clock", OffsetClock(timedelta(minutes=11)))  # type: ignore[attr-defined]
    assert _action(client, w, aid, "activate").status_code == 200
    # Échéance dépassée de longtemps : la clôture par défaut retient la fin prévue, sans antidatage abusif.
    monkeypatch.setattr(client.app.state, "clock", OffsetClock(timedelta(minutes=14)))  # type: ignore[attr-defined]
    settings = get_settings()
    original = settings.assignment_backdate_tolerance
    settings.assignment_backdate_tolerance = timedelta(minutes=1)
    try:
        done = _action(client, w, aid, "complete", {})
    finally:
        settings.assignment_backdate_tolerance = original
    assert done.status_code == 200, done.text
    assert datetime.fromisoformat(done.json()["valid_to"]) == datetime.fromisoformat(planned_end)


def test_sec1c03_start_beyond_planning_horizon_is_refused(client: TestClient, w: World) -> None:
    far = _now() + get_settings().assignment_max_horizon + timedelta(days=1)
    assert _reasons(_create(client, w, _vehicle(client, w), _driver(client, w), start=far)) == [
        "ASSIGNMENT_TOO_FAR_AHEAD"
    ]


def test_sec1c_r03_activation_instant_is_recorded(
    client: TestClient, w: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    immediate = _create(client, w, _vehicle(client, w), _driver(client, w)).json()
    assert immediate["activated_at"] is not None
    planned = _create(
        client, w, _vehicle(client, w), _driver(client, w), start=_now() + timedelta(minutes=10)
    ).json()
    assert planned["activated_at"] is None
    monkeypatch.setattr(client.app.state, "clock", OffsetClock(timedelta(minutes=13)))  # type: ignore[attr-defined]
    activated = _action(client, w, planned["vehicle_assignment_id"], "activate").json()
    late = datetime.fromisoformat(activated["activated_at"]) - datetime.fromisoformat(activated["valid_from"])
    assert late >= timedelta(minutes=2)  # prise de poste tardive visible, pas confondue avec le début prévu


def test_sec1c_r06_assignment_writers_can_read_driver_documents() -> None:
    """Les motifs du 422 (échéances de permis/habilitation) ne sont pas filtrés : tout rôle qui écrit une
    affectation doit lire permis et habilitations, à la même portée (sinon fuite contournant SEC1C-06)."""
    from app.authz.matrix import load_matrix

    perms = load_matrix().permissions
    for name in ("create", "update", "end"):
        for role, scopes in perms[f"assignment.vehicle_assignment.{name}"].grants.items():
            for document in ("workforce.driver_license.read", "workforce.driver_qualification.read"):
                assert set(scopes) <= set(perms[document].grants.get(role, ())), (name, role, document)


def test_sec1c_r11_site_move_without_open_assignment_and_db_guard(
    client: TestClient, w: World, app_engine: Engine
) -> None:
    vehicle, driver = _vehicle(client, w), _driver(client, w)
    for url, headers in (
        (f"{API}/vehicles/{vehicle}", w.t.admin.headers),
        (f"{API}/drivers/{driver}", w.hr.headers),
    ):
        moved = client.patch(
            url,
            headers={**headers, "If-Match": client.get(url, headers=headers).headers["ETag"]},
            json={"site_id": str(w.t.sites["S2"])},
        )
        assert moved.status_code == 200, moved.text  # le garde de base ne bloque pas un déplacement libre
    busy = _create(client, w, _vehicle(client, w), _driver(client, w)).json()
    with app_engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
        with pytest.raises(DBAPIError) as refused:
            conn.execute(
                text("UPDATE vehicle SET site_id = :s WHERE vehicle_id = :v"),
                {"s": str(w.t.sites["S2"]), "v": busy["vehicle_id"]},
            )
        assert getattr(refused.value.orig, "sqlstate", None) == "MF004"
        conn.rollback()
