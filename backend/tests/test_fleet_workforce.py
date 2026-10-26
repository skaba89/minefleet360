"""Tranche 1b — US-1.11 à US-1.21 : catégories, véhicules, conducteurs, permis, habilitations, échéances."""

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.workforce.validity import derive_validity
from tests.conftest import API, Account, Api, TenantFixture


@pytest.fixture
def fleet(api: Api) -> tuple[TenantFixture, Account]:
    t = api.tenant()
    return t, api.user(t, "HR")


def _category(client: TestClient, t: TenantFixture, code: str) -> str:
    cats = client.get(f"{API}/vehicle-categories", headers=t.admin.headers).json()
    return next(c["vehicle_category_id"] for c in cats if c["code"] == code)


def _vehicle(client: TestClient, t: TenantFixture, headers: dict[str, str] | None = None, **extra: object):  # type: ignore[no-untyped-def]
    body = {
        "site_id": str(t.sites["S1"]),
        "vehicle_category_id": _category(client, t, "RIGID_DUMP_TRUCK"),
        "fleet_number": f"P-{uuid.uuid4().hex[:6]}",
        **extra,
    }
    return client.post(f"{API}/vehicles", headers=headers or t.admin.headers, json=body)


def _driver(client: TestClient, t: TenantFixture, hr: Account, **extra: object):  # type: ignore[no-untyped-def]
    body = {
        "site_id": str(t.sites["S1"]),
        "employee_number": f"M-{uuid.uuid4().hex[:6]}",
        "last_name": "Nom-Test",
        "first_name": "Prénom",
        **extra,
    }
    return client.post(f"{API}/drivers", headers=hr.headers, json=body)


def _etag(client: TestClient, url: str, headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "If-Match": client.get(url, headers=headers).headers["ETag"]}


# --- US-1.11 Catégories -------------------------------------------------------------------------------


def test_us111_catalog_copied_at_tenant_creation(client: TestClient, api: Api) -> None:
    t = api.tenant()
    cats = client.get(f"{API}/vehicle-categories", headers=t.admin.headers).json()
    assert len(cats) == 15
    by_code = {c["code"]: c for c in cats}
    assert by_code["LIGHT_VEHICLE"]["required_license_categories"] == ["B"]
    assert by_code["BULLDOZER"]["required_license_categories"] == []
    other = api.tenant()
    foreign = client.get(
        f"{API}/vehicle-categories/{cats[0]['vehicle_category_id']}", headers=other.admin.headers
    )
    assert foreign.status_code == 404


# --- US-1.12 à US-1.15 Véhicules ----------------------------------------------------------------------


def test_us112_create_vehicle_and_uniqueness(client: TestClient, api: Api) -> None:
    t, other = api.tenant(), api.tenant()
    created = _vehicle(client, t, fleet_number="CB-01", registration_number="RC-1234-A")
    assert created.status_code == 201 and created.json()["status"] == "AVAILABLE"
    dup_fleet = _vehicle(client, t, fleet_number="cb-01")
    dup_reg = _vehicle(client, t, registration_number="rc 1234a")
    assert (dup_fleet.status_code, dup_fleet.json()["code"]) == (409, "DUPLICATE_FLEET_NUMBER")
    assert (dup_reg.status_code, dup_reg.json()["code"]) == (409, "DUPLICATE_REGISTRATION")
    assert _vehicle(client, other, fleet_number="CB-01", registration_number="RC-1234-A").status_code == 201
    history = client.get(
        f"{API}/vehicles/{created.json()['vehicle_id']}/status-history", headers=t.admin.headers
    )
    assert [(h["from_status"], h["to_status"]) for h in history.json()] == [(None, "AVAILABLE")]


def test_us112_references_and_permissions(client: TestClient, api: Api) -> None:
    t, other = api.tenant(), api.tenant()
    ops_s1 = api.user(t, "OPS_MANAGER", "SITE", "S1")
    out_of_scope = _vehicle(client, t, ops_s1.headers, site_id=str(t.sites["S2"]))
    foreign_cat = _vehicle(client, t, vehicle_category_id=_category(client, other, "BULLDOZER"))
    assert (out_of_scope.status_code, out_of_scope.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    assert (foreign_cat.status_code, foreign_cat.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    assert _vehicle(client, t, ops_s1.headers).status_code == 201
    hr = api.user(t, "HR")
    assert _vehicle(client, t, hr.headers).status_code == 403
    year = _vehicle(client, t, model_year=1800)
    assert year.status_code == 422


def test_us114_status_machine_reason_and_history(client: TestClient, api: Api) -> None:
    t = api.tenant()
    vid = _vehicle(client, t).json()["vehicle_id"]
    url = f"{API}/vehicles/{vid}"
    no_reason = client.post(
        f"{url}/status", headers=_etag(client, url, t.admin.headers), json={"status": "IMMOBILIZED"}
    )
    assert (no_reason.status_code, no_reason.json()["code"]) == (422, "STATUS_REASON_REQUIRED")
    ok = client.post(
        f"{url}/status",
        headers=_etag(client, url, t.admin.headers),
        json={"status": "IMMOBILIZED", "reason_code": "BREAKDOWN"},
    )
    assert ok.status_code == 200 and ok.json()["status_reason_code"] == "BREAKDOWN"
    bad = client.post(
        f"{url}/status", headers=_etag(client, url, t.admin.headers), json={"status": "IMMOBILIZED"}
    )
    assert (bad.status_code, bad.json()["code"]) == (422, "VEHICLE_STATUS_TRANSITION_INVALID")
    back = client.post(
        f"{url}/status", headers=_etag(client, url, t.admin.headers), json={"status": "AVAILABLE"}
    )
    assert back.status_code == 200 and back.json()["status_reason_code"] is None
    history = client.get(f"{url}/status-history", headers=t.admin.headers).json()
    assert [h["to_status"] for h in history] == ["AVAILABLE", "IMMOBILIZED", "AVAILABLE"]
    stale = client.post(
        f"{url}/status", headers={**t.admin.headers, "If-Match": '"1"'}, json={"status": "IN_MAINTENANCE"}
    )
    assert stale.json()["code"] == "VERSION_CONFLICT"


def test_us115_retire_is_terminal_and_hidden_by_default(client: TestClient, api: Api) -> None:
    t = api.tenant()
    vid = _vehicle(client, t).json()["vehicle_id"]
    url = f"{API}/vehicles/{vid}"
    retired = client.post(
        f"{url}/retire", headers=_etag(client, url, t.admin.headers), json={"reason_code": "SOLD"}
    )
    assert retired.status_code == 200, retired.text
    assert retired.json()["decommissioned_on"] is not None
    again = client.post(
        f"{url}/status", headers=_etag(client, url, t.admin.headers), json={"status": "AVAILABLE"}
    )
    assert again.json()["code"] == "VEHICLE_STATUS_TRANSITION_INVALID"
    edit = client.patch(url, headers=_etag(client, url, t.admin.headers), json={"notes": "x"})
    assert edit.json()["code"] == "VEHICLE_STATUS_TRANSITION_INVALID"
    default = client.get(f"{API}/vehicles", headers=t.admin.headers).json()["items"]
    included = client.get(
        f"{API}/vehicles", headers=t.admin.headers, params={"include_retired": "true"}
    ).json()
    assert vid not in {v["vehicle_id"] for v in default}
    assert vid in {v["vehicle_id"] for v in included["items"]}


def test_us113_site_scoped_dispatcher(client: TestClient, api: Api) -> None:
    t = api.tenant()
    v1 = _vehicle(client, t).json()["vehicle_id"]
    v2 = _vehicle(client, t, site_id=str(t.sites["S2"])).json()["vehicle_id"]
    disp = api.user(t, "DISPATCHER", "SITE", "S1")
    listed = client.get(f"{API}/vehicles", headers=disp.headers).json()
    assert [v["vehicle_id"] for v in listed["items"]] == [v1] and listed["total"] == 1
    assert client.get(f"{API}/vehicles/{v2}", headers=disp.headers).status_code == 404
    url = f"{API}/vehicles/{v1}"
    resp = client.post(
        f"{url}/status", headers=_etag(client, url, disp.headers), json={"status": "IN_MAINTENANCE"}
    )
    assert resp.status_code == 200
    assert client.patch(url, headers=_etag(client, url, disp.headers), json={"notes": "x"}).status_code == 403


def test_ct9_unknown_or_tenant_query_parameters_rejected(client: TestClient, api: Api) -> None:
    t = api.tenant()
    for params in ({"tenant_id": str(uuid.uuid4())}, {"inconnu": "1"}):
        resp = client.get(f"{API}/vehicles", headers=t.admin.headers, params=params)
        assert (resp.status_code, resp.json()["code"]) == (422, "VALIDATION_ERROR")
    # L'ordre D-05 est préservé : sans jeton, 401 avant la validation des paramètres.
    assert client.get(f"{API}/vehicles", params={"inconnu": "1"}).status_code == 401


def test_us113_registration_search_is_normalized(client: TestClient, api: Api) -> None:
    t = api.tenant()
    vid = _vehicle(client, t, registration_number="AB-123-CD").json()["vehicle_id"]
    found = client.get(
        f"{API}/vehicles", headers=t.admin.headers, params={"registration_number": "ab 123cd"}
    ).json()
    assert [v["vehicle_id"] for v in found["items"]] == [vid]


# --- US-1.16, US-1.17, US-1.21 Conducteurs ------------------------------------------------------------


def test_us116_create_driver_rules(client: TestClient, fleet: tuple[TenantFixture, Account]) -> None:
    t, hr = fleet
    first = _driver(client, t, hr, employee_number="MAT-1", last_name="Camara", first_name="Aïssatou")
    assert first.status_code == 201 and first.json()["status"] == "ACTIVE" and "warnings" not in first.json()
    homonym = _driver(client, t, hr, last_name="CAMARA", first_name="aissatou")
    assert homonym.status_code == 201 and homonym.json()["warnings"] == ["POSSIBLE_DUPLICATE"]
    dup = _driver(client, t, hr, employee_number="MAT-1")
    assert (dup.status_code, dup.json()["code"]) == (409, "DUPLICATE_EMPLOYEE_NUMBER")
    forbidden = _driver(client, t, hr, date_of_birth="1990-01-01")
    assert (forbidden.status_code, forbidden.json()["code"]) == (422, "VALIDATION_ERROR")
    as_admin = _driver(client, t, t.admin)
    assert (as_admin.status_code, as_admin.json()["code"]) == (403, "PERMISSION_DENIED")


def test_us117_masking_by_role(client: TestClient, api: Api, fleet: tuple[TenantFixture, Account]) -> None:
    t, hr = fleet
    driver = _driver(client, t, hr, phone="+224000000555", hire_date="2020-02-01").json()
    url = f"{API}/drivers/{driver['driver_id']}"
    hr_view = client.get(url, headers=hr.headers).json()
    assert hr_view["phone"] == "+224000000555" and hr_view["hire_date"] == "2020-02-01"
    for role, scope, site in (
        ("DISPATCHER", "SITE", "S1"),
        ("OPS_MANAGER", "TENANT", None),
        ("AUDITOR", "TENANT", None),
    ):
        viewer = api.user(t, role, scope, site)
        raw = client.get(url, headers=viewer.headers).text
        assert "+224000000555" not in raw and '"phone"' not in raw and '"hire_date"' not in raw, role
        assert '"employee_number"' in raw
    assert client.get(url, headers=t.admin.headers).status_code == 403
    audit = client.get(
        f"{API}/audit-events", headers=t.admin.headers, params={"entity_id": driver["driver_id"]}
    ).text
    assert "+224000000555" not in audit


def test_us121_status_change_requires_reason(
    client: TestClient, fleet: tuple[TenantFixture, Account]
) -> None:
    t, hr = fleet
    driver_id = _driver(client, t, hr).json()["driver_id"]
    url = f"{API}/drivers/{driver_id}"
    missing = client.post(
        f"{url}/status", headers=_etag(client, url, hr.headers), json={"status": "INACTIVE"}
    )
    assert (missing.status_code, missing.json()["code"]) == (422, "STATUS_REASON_REQUIRED")
    ok = client.post(
        f"{url}/status",
        headers=_etag(client, url, hr.headers),
        json={"status": "INACTIVE", "exit_date": "2026-10-01"},
    )
    assert ok.status_code == 200 and ok.json()["exit_date"] == "2026-10-01"
    back = client.post(f"{url}/status", headers=_etag(client, url, hr.headers), json={"status": "ACTIVE"})
    assert back.status_code == 200 and back.json()["exit_date"] is None


def test_us117_site_change_needs_scope(client: TestClient, api: Api) -> None:
    t = api.tenant()
    hr_s1 = api.user(t, "HR", "SITE", "S1")
    driver_id = _driver(client, t, hr_s1).json()["driver_id"]
    url = f"{API}/drivers/{driver_id}"
    resp = client.patch(url, headers=_etag(client, url, hr_s1.headers), json={"site_id": str(t.sites["S2"])})
    assert (resp.status_code, resp.json()["code"]) == (422, "REFERENCE_NOT_FOUND")


# --- US-1.18 à US-1.20 Permis, habilitations, échéances -----------------------------------------------


def test_us118_license_rules_and_number_masking(
    client: TestClient, api: Api, fleet: tuple[TenantFixture, Account]
) -> None:
    t, hr = fleet
    driver_id = _driver(client, t, hr).json()["driver_id"]
    url = f"{API}/drivers/{driver_id}/licenses"
    body = {
        "license_number": "PERMIS-FICTIF-4242",
        "category_code": "C",
        "issue_date": "2015-03-01",
        "expiry_date": "2016-03-01",
    }
    expired = client.post(url, headers=hr.headers, json=body)
    assert expired.status_code == 201 and expired.json()["validity"] == "EXPIRED"
    assert client.post(url, headers=hr.headers, json=body).json()["code"] == "DUPLICATE_LICENSE"
    renewed = client.post(
        url, headers=hr.headers, json={**body, "issue_date": "2025-01-01", "expiry_date": "2035-01-01"}
    )
    assert renewed.status_code == 201 and renewed.json()["validity"] == "VALID"
    bad = client.post(
        url, headers=hr.headers, json={**body, "issue_date": "2025-01-01", "expiry_date": "2025-01-01"}
    )
    assert bad.status_code == 422
    unknown = client.post(
        url,
        headers=hr.headers,
        json={**body, "category_code": "Z", "issue_date": "2024-01-01", "expiry_date": "2034-01-01"},
    )
    assert (unknown.status_code, unknown.json()["code"]) == (422, "REFERENCE_NOT_FOUND")
    ops = api.user(t, "OPS_MANAGER")
    assert "PERMIS-FICTIF-4242" not in client.get(url, headers=ops.headers).text
    assert client.post(url, headers=ops.headers, json=body).status_code == 403
    audit = client.get(f"{API}/audit-events", headers=t.admin.headers, params={"page_size": 200}).text
    assert "PERMIS-FICTIF-4242" not in audit


def test_us119_qualifications_overlap_hse_and_authorized_categories(
    client: TestClient, api: Api, fleet: tuple[TenantFixture, Account]
) -> None:
    t, hr = fleet
    driver_id = _driver(client, t, hr).json()["driver_id"]
    category = _category(client, t, "WHEEL_LOADER")
    url = f"{API}/drivers/{driver_id}/qualifications"
    body = {
        "qualification_type": "DRIVING_AUTHORIZATION",
        "vehicle_category_id": category,
        "valid_from": "2025-01-01",
        "valid_to": "2030-12-31",
    }
    created = client.post(url, headers=hr.headers, json=body)
    assert created.status_code == 201
    overlap = client.post(url, headers=hr.headers, json={**body, "valid_from": "2026-01-01"})
    assert (overlap.status_code, overlap.json()["code"]) == (409, "DUPLICATE_QUALIFICATION")
    hse = api.user(t, "HSE")
    assert client.post(url, headers=hse.headers, json=body).status_code == 403
    assert client.get(url, headers=hse.headers).status_code == 200
    assert client.get(f"{API}/drivers/{driver_id}", headers=hr.headers).json()["authorized_category_ids"] == [
        category
    ]
    q_id = created.json()["driver_qualification_id"]
    revoke = client.post(
        f"{API}/driver-qualifications/{q_id}/revoke",
        headers={**hr.headers, "If-Match": '"1"'},
        json={"status": "REVOKED"},
    )
    assert revoke.status_code == 200 and revoke.json()["validity"] == "REVOKED"
    assert (
        client.get(f"{API}/drivers/{driver_id}", headers=hr.headers).json()["authorized_category_ids"] == []
    )
    missing_cat = client.post(
        url, headers=hr.headers, json={**body, "vehicle_category_id": str(uuid.uuid4())}
    )
    assert (missing_cat.status_code, missing_cat.json()["code"]) == (422, "REFERENCE_NOT_FOUND")


def test_us120_expirations_listed_within_scope(
    client: TestClient, api: Api, fleet: tuple[TenantFixture, Account]
) -> None:
    t, hr = fleet
    other_t = api.tenant()
    other_hr = api.user(other_t, "HR")
    soon = (datetime.now(UTC) + timedelta(days=5)).date().isoformat()
    for tenant, account in ((t, hr), (other_t, other_hr)):
        driver_id = _driver(client, tenant, account).json()["driver_id"]
        client.post(
            f"{API}/drivers/{driver_id}/licenses",
            headers=account.headers,
            json={
                "license_number": f"PERMIS-FICTIF-{uuid.uuid4().hex[:4]}",
                "category_code": "B",
                "issue_date": "2020-01-01",
                "expiry_date": soon,
            },
        )
    items = client.get(f"{API}/workforce/expirations", headers=hr.headers).json()
    assert len(items) == 1 and items[0]["validity"] == "EXPIRING" and items[0]["kind"] == "LICENSE"


# --- D-23 : validité au fuseau du site ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("instant", "tz", "expected"),
    [
        (datetime(2026, 3, 10, 23, 30, tzinfo=UTC), "Africa/Conakry", "EXPIRING"),  # J 23:30 local
        (datetime(2026, 3, 10, 23, 30, tzinfo=UTC), "Africa/Lagos", "EXPIRED"),  # J+1 00:30 local
        (datetime(2026, 3, 10, 22, 59, 59, tzinfo=UTC), "Africa/Lagos", "EXPIRING"),  # J 23:59:59 local
        (datetime(2026, 3, 11, 0, 0, tzinfo=UTC), "Africa/Conakry", "EXPIRED"),  # J+1 00:00 local
        (datetime(2026, 1, 1, tzinfo=UTC), "Africa/Conakry", "VALID"),
        (datetime(2019, 1, 1, tzinfo=UTC), "Africa/Conakry", "NOT_YET_VALID"),
    ],
)
def test_d23_validity_boundaries_depend_on_site_timezone(instant: datetime, tz: str, expected: str) -> None:
    validity = derive_validity(
        stored_status="VALID",
        valid_from=date(2020, 1, 1),
        valid_until=date(2026, 3, 10),
        now=instant,
        tz=ZoneInfo(tz),
        warning_days=30,
    )
    assert validity == expected


def test_stored_status_takes_precedence_over_dates() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    tz = ZoneInfo("Africa/Conakry")
    assert (
        derive_validity(
            stored_status="SUSPENDED", valid_from=None, valid_until=None, now=now, tz=tz, warning_days=30
        )
        == "SUSPENDED"
    )


def test_masking_is_evaluated_per_record_site(client: TestClient, api: Api) -> None:
    """Revue sécurité 1b : HR sur S1 + DISPATCHER sur S2 ne voit pas le téléphone d'un conducteur de S2."""
    t = api.tenant()
    hr = api.user(t, "HR")
    mixed = api.user(t, "HR", "SITE", "S1")
    assert (
        client.post(
            f"{API}/role-assignments",
            headers=t.admin.headers,
            json={
                "user_account_id": str(mixed.user_id),
                "role_code": "DISPATCHER",
                "scope_type": "SITE",
                "site_id": str(t.sites["S2"]),
            },
        ).status_code
        == 201
    )
    on_s1 = _driver(client, t, hr, phone="+224000000101").json()["driver_id"]
    on_s2 = _driver(client, t, hr, site_id=str(t.sites["S2"]), phone="+224000000202").json()["driver_id"]
    assert client.get(f"{API}/drivers/{on_s1}", headers=mixed.headers).json()["phone"] == "+224000000101"
    s2_view = client.get(f"{API}/drivers/{on_s2}", headers=mixed.headers)
    assert s2_view.status_code == 200 and "phone" not in s2_view.json()


def test_restricted_driver_fields_never_valued_in_audit(
    client: TestClient, fleet: tuple[TenantFixture, Account]
) -> None:
    t, hr = fleet
    driver_id = _driver(client, t, hr, employment_type="TEMP_AGENCY", hire_date="2021-05-05").json()[
        "driver_id"
    ]
    url = f"{API}/drivers/{driver_id}"
    client.patch(
        url,
        headers=_etag(client, url, hr.headers),
        json={"employment_type": "EMPLOYEE", "last_name": "Autre"},
    )
    events = client.get(
        f"{API}/audit-events", headers=t.admin.headers, params={"entity_id": driver_id}
    ).json()["items"]
    dumped = str([(e["before_data"], e["after_data"]) for e in events])
    assert "TEMP_AGENCY" not in dumped and "2021-05-05" not in dumped and "Autre" in dumped
    assert any("employment_type" in (e["changed_fields"] or []) for e in events)
