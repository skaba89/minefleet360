"""Lot 2a — missions de transport et rotations (docs/PLAN_LOT2.md, US-2.01 à US-2.04)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from tests.conftest import API, Api
from tests.test_assignment import World, _create, _driver, _vehicle, w  # noqa: F401  (fixture w)


def _now() -> datetime:
    return datetime.now(UTC)


def _refs(client: TestClient, w: World, site: str = "S1") -> dict[str, str]:  # noqa: F811
    suffix = uuid.uuid4().hex[:6].upper()
    places = {}
    for code, kind in ((f"FOSSE-{suffix}", "LOADING_POINT"), (f"VERSE-{suffix}", "DUMP_POINT")):
        resp = client.post(
            f"{API}/site-locations",
            headers=w.t.admin.headers,
            json={"site_id": str(w.t.sites[site]), "code": code, "name": f"Lieu {code}", "kind": kind},
        )
        assert resp.status_code == 201, resp.text
        places[kind] = resp.json()["site_location_id"]
    material = client.post(
        f"{API}/materials", headers=w.t.admin.headers, json={"code": f"BAUX-{suffix}", "name": "Bauxite"}
    )
    assert material.status_code == 201, material.text
    return {
        "origin": places["LOADING_POINT"],
        "destination": places["DUMP_POINT"],
        "material": material.json()["material_id"],
    }


def _assignment(client: TestClient, w: World, site: str = "S1", start: datetime | None = None) -> dict:  # type: ignore[type-arg]  # noqa: F811
    created = _create(client, w, _vehicle(client, w, site), _driver(client, w, site), start=start)
    assert created.status_code == 201, created.text
    return created.json()


def _mission(client: TestClient, w: World, assignment: dict, refs: dict[str, str], headers=None):  # type: ignore[no-untyped-def,type-arg]  # noqa: F811
    return client.post(
        f"{API}/missions",
        headers=headers or w.ops.headers,
        json={
            "vehicle_assignment_id": assignment["vehicle_assignment_id"],
            "origin_location_id": refs["origin"],
            "destination_location_id": refs["destination"],
            "material_id": refs["material"],
            "planned_start": _now().isoformat(),
            "planned_rotations": 2,
        },
    )


def _event(client: TestClient, w: World, mission_id: str, event_type: str, headers=None, **extra):  # type: ignore[no-untyped-def]  # noqa: F811
    auth = headers or w.ops.headers
    url = f"{API}/missions/{mission_id}"
    version = client.get(url, headers=auth).headers["ETag"]
    return client.post(
        f"{url}/events", headers={**auth, "If-Match": version}, json={"event_type": event_type, **extra}
    )


def test_referentials_codes_scope_and_permissions(client: TestClient, w: World) -> None:  # noqa: F811
    refs = _refs(client, w)
    listed = client.get(
        f"{API}/site-locations", headers=w.dispatcher.headers, params={"site_id": str(w.t.sites["S1"])}
    )
    assert {loc["site_location_id"] for loc in listed.json()} >= {refs["origin"], refs["destination"]}
    code = next(loc["code"] for loc in listed.json() if loc["site_location_id"] == refs["origin"])
    dup = client.post(
        f"{API}/site-locations",
        headers=w.t.admin.headers,
        json={"site_id": str(w.t.sites["S1"]), "code": code, "name": "Doublon", "kind": "STOCKPILE"},
    )
    assert (dup.status_code, dup.json()["code"]) == (409, "DUPLICATE_LOCATION_CODE")
    # Même code sur un autre site : accepté (unicité par site).
    other_site = client.post(
        f"{API}/site-locations",
        headers=w.t.admin.headers,
        json={"site_id": str(w.t.sites["S2"]), "code": code, "name": "Autre site", "kind": "STOCKPILE"},
    )
    assert other_site.status_code == 201
    denied = client.post(
        f"{API}/materials", headers=w.dispatcher.headers, json={"code": "X", "name": "Interdit"}
    )
    assert denied.status_code == 403


def test_mission_creation_references(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    refs = _refs(client, w)
    assignment = _assignment(client, w)
    created = _mission(client, w, assignment, refs)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "ASSIGNED" and body["rotations_completed"] == 0
    assert body["vehicle_fleet_number"].startswith("P-") and body["material_name"] == "Bauxite"
    assert [
        e["event_type"]
        for e in client.get(f"{API}/missions/{body['mission_id']}", headers=w.ops.headers).json()["events"]
    ] == ["CREATED"]

    same = _mission(client, w, assignment, {**refs, "destination": refs["origin"]})
    assert same.status_code == 422
    s2_refs = _refs(client, w, "S2")
    wrong_site = _mission(client, w, assignment, {**refs, "origin": s2_refs["origin"]})
    assert (wrong_site.status_code, wrong_site.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    other = api.tenant()
    foreign = _mission(client, w, assignment, refs, headers=api.user(other, "OPS_MANAGER").headers)
    assert (foreign.status_code, foreign.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    assert _mission(client, w, assignment, refs, headers=w.hr.headers).status_code == 403


def test_full_lifecycle_with_two_rotations(client: TestClient, w: World) -> None:  # noqa: F811
    refs = _refs(client, w)
    mission = _mission(client, w, _assignment(client, w), refs).json()
    mid = mission["mission_id"]
    sequence = [
        ("DEPARTED", "EN_ROUTE_EMPTY"),
        ("ARRIVED_LOADING", "LOADING"),
        ("LOADED", "EN_ROUTE_LOADED"),
        ("ARRIVED_UNLOADING", "UNLOADING"),
        ("UNLOADED", "EN_ROUTE_EMPTY"),
        ("ARRIVED_LOADING", "LOADING"),
        ("LOADED", "EN_ROUTE_LOADED"),
        ("ARRIVED_UNLOADING", "UNLOADING"),
        ("COMPLETED", "COMPLETED"),
    ]
    for event, expected in sequence:
        resp = _event(client, w, mid, event, headers=w.dispatcher.headers)
        assert resp.status_code == 200, (event, resp.text)
        assert resp.json()["status"] == expected
    final = client.get(f"{API}/missions/{mid}", headers=w.ops.headers).json()
    assert final["rotations_completed"] == 2
    assert [r["status"] for r in final["rotations"]] == ["COMPLETED", "COMPLETED"]
    assert all(r["cycle_seconds"] is not None and r["cycle_seconds"] >= 0 for r in final["rotations"])
    assert len(final["events"]) == 1 + len(sequence)
    assert "tonn" not in str(final).lower()  # aucun tonnage en 2a (RM-070, RM-072)
    after = _event(client, w, mid, "DEPARTED")
    assert (after.status_code, after.json()["code"]) == (409, "MISSION_STATE_INVALID")
    events = client.get(f"{API}/audit-events", headers=w.t.admin.headers, params={"entity_id": mid}).json()
    assert events["total"] == 1 + len(sequence)


def test_invalid_transitions_and_reasons(client: TestClient, w: World) -> None:  # noqa: F811
    mid = _mission(client, w, _assignment(client, w), _refs(client, w)).json()["mission_id"]
    skipped = _event(client, w, mid, "LOADED")
    assert (skipped.status_code, skipped.json()["code"]) == (409, "MISSION_STATE_INVALID")
    no_reason = _event(client, w, mid, "SUSPENDED")
    assert (no_reason.status_code, no_reason.json()["code"]) == (422, "STATUS_REASON_REQUIRED")
    early_complete = _event(client, w, mid, "COMPLETED")
    assert early_complete.status_code == 409
    cancelled = _event(client, w, mid, "CANCELLED", reason_code="PLAN_CHANGED")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"


def test_departure_requires_active_compliant_assignment(client: TestClient, w: World) -> None:  # noqa: F811
    refs = _refs(client, w)
    planned = _assignment(client, w, start=_now() + timedelta(days=1))
    mid = _mission(client, w, planned, refs).json()["mission_id"]
    refused = _event(client, w, mid, "DEPARTED")
    assert (refused.status_code, refused.json()["code"]) == (422, "MISSION_NOT_ELIGIBLE")
    assert "ASSIGNMENT_NOT_ACTIVE" in [r["code"] for r in refused.json()["details"]["reasons"]]

    active = _assignment(client, w)
    mid2 = _mission(client, w, active, refs).json()["mission_id"]
    lic = client.get(f"{API}/drivers/{active['driver_id']}/licenses", headers=w.hr.headers).json()[0]
    client.patch(
        f"{API}/driver-licenses/{lic['driver_license_id']}",
        headers={**w.hr.headers, "If-Match": f'"{lic["row_version"]}"'},
        json={"status": "WITHDRAWN"},
    )
    non_compliant = _event(client, w, mid2, "DEPARTED")
    assert (non_compliant.status_code, non_compliant.json()["code"]) == (422, "MISSION_NOT_ELIGIBLE")
    assert "LICENSE_EXPIRED" in [r["code"] for r in non_compliant.json()["details"]["reasons"]]


def test_one_running_mission_per_vehicle(client: TestClient, w: World) -> None:  # noqa: F811
    refs = _refs(client, w)
    assignment = _assignment(client, w)
    first = _mission(client, w, assignment, refs).json()["mission_id"]
    second = _mission(client, w, assignment, refs).json()["mission_id"]
    assert _event(client, w, first, "DEPARTED").status_code == 200
    busy = _event(client, w, second, "DEPARTED")
    assert (busy.status_code, busy.json()["code"]) == (409, "VEHICLE_ON_MISSION")


def test_resent_event_is_not_duplicated(client: TestClient, w: World) -> None:  # noqa: F811
    mid = _mission(client, w, _assignment(client, w), _refs(client, w)).json()["mission_id"]
    key = str(uuid.uuid4())
    first = _event(client, w, mid, "DEPARTED", client_event_id=key)
    again = _event(client, w, mid, "DEPARTED", client_event_id=key)  # renvoi après coupure réseau
    assert first.status_code == again.status_code == 200
    assert again.json()["status"] == "EN_ROUTE_EMPTY"
    detail = client.get(f"{API}/missions/{mid}", headers=w.ops.headers).json()
    assert [e["event_type"] for e in detail["events"]].count("DEPARTED") == 1
    reused = _event(client, w, mid, "ARRIVED_LOADING", client_event_id=key)
    assert (reused.status_code, reused.json()["code"]) == (409, "CONFLICT")


def test_breakdown_suspension_and_reassignment(client: TestClient, w: World) -> None:  # noqa: F811
    refs = _refs(client, w)
    mission = _mission(client, w, _assignment(client, w), refs).json()
    mid = mission["mission_id"]
    for event in ("DEPARTED", "ARRIVED_LOADING"):
        assert _event(client, w, mid, event).status_code == 200
    suspended = _event(client, w, mid, "SUSPENDED", reason_code="BREAKDOWN")
    assert (
        suspended.json()["status"] == "SUSPENDED"
        and suspended.json()["status_before_suspension"] == "LOADING"
    )
    spare = _assignment(client, w)
    reassigned = _event(client, w, mid, "REASSIGNED", vehicle_assignment_id=spare["vehicle_assignment_id"])
    assert reassigned.status_code == 200, reassigned.text
    body = reassigned.json()
    assert body["vehicle_id"] == spare["vehicle_id"] and body["status"] == "SUSPENDED"
    assert [r["status"] for r in body["rotations"]] == ["ABORTED"]  # le cycle en cours est perdu
    resumed = _event(client, w, mid, "RESUMED")
    assert resumed.json()["status"] == "ASSIGNED"
    assert _event(client, w, mid, "DEPARTED").json()["status"] == "EN_ROUTE_EMPTY"


def test_declared_time_is_bounded(client: TestClient, w: World) -> None:  # noqa: F811
    mid = _mission(client, w, _assignment(client, w), _refs(client, w)).json()["mission_id"]
    future = _event(client, w, mid, "DEPARTED", occurred_at=(_now() + timedelta(hours=1)).isoformat())
    assert future.status_code == 422
    assert _event(client, w, mid, "DEPARTED").status_code == 200
    earlier = _event(
        client, w, mid, "ARRIVED_LOADING", occurred_at=(_now() - timedelta(minutes=5)).isoformat()
    )
    assert earlier.status_code == 422  # avant le dernier événement : ordre chronologique préservé


def test_site_scope_and_append_only_events(client: TestClient, w: World) -> None:  # noqa: F811
    s2 = _mission(client, w, _assignment(client, w, "S2"), _refs(client, w, "S2")).json()
    hidden = client.get(f"{API}/missions/{s2['mission_id']}", headers=w.dispatcher.headers)
    assert hidden.status_code == 404
    listed = client.get(f"{API}/missions", headers=w.dispatcher.headers).json()["items"]
    assert s2["mission_id"] not in {m["mission_id"] for m in listed}
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            with pytest.raises(DBAPIError) as refused:
                conn.execute(
                    text("UPDATE mission_event SET reason = 'OTHER' WHERE mission_id = :m"),
                    {"m": s2["mission_id"]},
                )
            assert getattr(refused.value.orig, "sqlstate", None) in ("MF001", "42501")
            conn.rollback()
    finally:
        engine.dispose()


def test_reassignment_is_traceable(client: TestClient, w: World) -> None:  # noqa: F811
    """L2A-R-01 : la chronologie et l'audit disent qui a pris le relais, et de qui."""
    first = _assignment(client, w)
    mid = _mission(client, w, first, _refs(client, w)).json()["mission_id"]
    assert _event(client, w, mid, "SUSPENDED", reason_code="BREAKDOWN").status_code == 200
    spare = _assignment(client, w)
    reassigned = _event(client, w, mid, "REASSIGNED", vehicle_assignment_id=spare["vehicle_assignment_id"])
    assert reassigned.status_code == 200, reassigned.text
    crews = [(e["event_type"], e["vehicle_assignment_id"]) for e in reassigned.json()["events"]]
    assert crews == [
        ("CREATED", first["vehicle_assignment_id"]),
        ("SUSPENDED", first["vehicle_assignment_id"]),
        ("REASSIGNED", spare["vehicle_assignment_id"]),
    ]
    audit = client.get(
        f"{API}/audit-events",
        headers=w.t.admin.headers,
        params={"entity_id": mid, "action": "mission.reassigned"},
    ).json()["items"][0]
    assert audit["before_data"]["driver_id"] == first["driver_id"]
    assert audit["after_data"]["driver_id"] == spare["driver_id"]
    assert set(audit["changed_fields"]) >= {"vehicle_assignment_id", "vehicle_id", "driver_id"}


def test_driver_name_follows_assignment_read_rights(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    """L2A-R-02 : FINANCE et un chef d'atelier d'un autre site lisent la mission sans le conducteur (D-10)."""
    mid = _mission(client, w, _assignment(client, w), _refs(client, w)).json()["mission_id"]
    seen = client.get(f"{API}/missions/{mid}", headers=w.ops.headers).json()
    assert seen["driver_display_name"] and seen["driver_id"]
    for reader in (
        api.user(w.t, "FINANCE"),
        api.user(w.t, "WORKSHOP_CHIEF"),  # portée tenant : lit les affectations de son seul site
    ):
        masked = client.get(f"{API}/missions/{mid}", headers=reader.headers)
        assert masked.status_code == 200, masked.text
        assert masked.json()["driver_display_name"] is None and masked.json()["driver_id"] is None
        listed = client.get(f"{API}/missions", headers=reader.headers).json()["items"]
        assert all(m["driver_display_name"] is None for m in listed)
    local_chief = api.user(w.t, "WORKSHOP_CHIEF", "SITE", "S1")
    assert client.get(f"{API}/missions/{mid}", headers=local_chief.headers).json()["driver_display_name"]


def test_departure_checks_use_server_time(client: TestClient, w: World) -> None:  # noqa: F811
    """L2A-R-03 : un départ antidaté avant la fin de l'affectation reste refusé une fois celle-ci échue."""
    assignment = _assignment(client, w, start=_now() - timedelta(minutes=10))
    mid = _mission(client, w, assignment, _refs(client, w)).json()["mission_id"]
    created_at = client.get(f"{API}/missions/{mid}", headers=w.ops.headers).json()["events"][0]["occurred_at"]
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            # Affectation encore ACTIVE mais échue une milliseconde après la création de la mission.
            conn.execute(
                text(
                    "UPDATE vehicle_assignment"
                    " SET valid_to = CAST(:at AS timestamptz) + interval '1 millisecond'"
                    " WHERE vehicle_assignment_id = :a"
                ),
                {"at": created_at, "a": assignment["vehicle_assignment_id"]},
            )
    finally:
        engine.dispose()
    backdated = _event(client, w, mid, "DEPARTED", occurred_at=created_at)
    assert (backdated.status_code, backdated.json()["code"]) == (422, "MISSION_NOT_ELIGIBLE")
    assert "ASSIGNMENT_ENDED" in [r["code"] for r in backdated.json()["details"]["reasons"]]


def test_event_id_of_another_mission_is_not_revealed(client: TestClient, w: World) -> None:  # noqa: F811
    """L2A-R-05 : identifiant déjà pris ailleurs → conflit ordinaire, sans rejeu de l'autre mission."""
    refs = _refs(client, w)
    first = _mission(client, w, _assignment(client, w), refs).json()["mission_id"]
    second = _mission(client, w, _assignment(client, w), refs).json()["mission_id"]
    key = str(uuid.uuid4())
    assert _event(client, w, first, "DEPARTED", client_event_id=key).status_code == 200
    reused = _event(client, w, second, "DEPARTED", client_event_id=key)
    assert (reused.status_code, reused.json()["code"]) == (409, "CONFLICT")
    assert "mission_id" not in str(reused.json()["details"] or "")
    still = client.get(f"{API}/missions/{second}", headers=w.ops.headers).json()
    assert still["status"] == "ASSIGNED" and len(still["events"]) == 1
