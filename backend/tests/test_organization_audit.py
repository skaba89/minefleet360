"""US-1.01, US-1.03, US-1.26, US-1.27, US-1.32 — tenants, sites, journal d'audit, amorçage plateforme."""

import uuid

from fastapi.testclient import TestClient

from app.cli import create_platform_admin
from tests.conftest import API, PASSWORD, Api, unique_code


def _tenant_body(code: str, name: str | None = None) -> dict[str, str]:
    return {
        "code": code,
        "legal_name": name or f"Société fictive {code}",
        "display_name": f"Fictive {code}",
        "admin_email": f"admin.{code}@example.com",
        "admin_display_name": "Admin Fictif",
    }


def test_us101_duplicates_and_reserved_codes(client: TestClient, api: Api) -> None:
    t = api.tenant()
    platform = api.platform()
    dup_code = client.post(f"{API}/platform/tenants", headers=platform, json=_tenant_body(t.code))
    dup_name = client.post(
        f"{API}/platform/tenants",
        headers=platform,
        json=_tenant_body(unique_code(), f"  SOCIÉTÉ   fictive {t.code} "),
    )
    reserved = client.post(f"{API}/platform/tenants", headers=platform, json=_tenant_body("mf-platform"))
    bad = client.post(f"{API}/platform/tenants", headers=platform, json=_tenant_body("Majuscules!"))
    assert (dup_code.status_code, dup_code.json()["code"]) == (409, "DUPLICATE_WORKSPACE_CODE")
    assert (dup_name.status_code, dup_name.json()["code"]) == (409, "DUPLICATE_TENANT_NAME")
    assert (reserved.status_code, reserved.json()["code"]) == (422, "TENANT_CODE_RESERVED")
    assert (bad.status_code, bad.json()["code"]) == (422, "VALIDATION_ERROR")


def test_us101_a6_platform_admin_has_no_business_access(client: TestClient, api: Api) -> None:
    for path in ("/sites", "/users", "/audit-events", "/tenant"):
        resp = client.get(f"{API}{path}", headers=api.platform())
        assert resp.status_code == 403, path


def test_us132_platform_admin_bootstrap_refused_twice() -> None:
    assert create_platform_admin("autre.admin@example.com", "Autre", PASSWORD) == 3


def test_us103_sites_unique_per_tenant_and_validation(client: TestClient, api: Api) -> None:
    a, b = api.tenant(), api.tenant()
    dup = client.post(
        f"{API}/sites", headers=a.admin.headers, json={"code": "S1", "name": "Doublon", "site_type": "MINE"}
    )
    assert dup.status_code == 409 and dup.json()["code"] == "DUPLICATE_SITE_CODE"
    other = client.post(
        f"{API}/sites", headers=b.admin.headers, json={"code": "S9", "name": "Neuf", "site_type": "PORT"}
    )
    assert other.status_code == 201
    same_code_elsewhere = client.post(
        f"{API}/sites", headers=b.admin.headers, json={"code": "S1x", "name": "Libre", "site_type": "DEPOT"}
    )
    assert same_code_elsewhere.status_code == 201
    tz = client.post(
        f"{API}/sites",
        headers=a.admin.headers,
        json={"code": "TZ", "name": "Fuseau", "site_type": "MINE", "timezone": "Mars/Olympus"},
    )
    assert tz.status_code == 422 and tz.json()["code"] == "VALIDATION_ERROR"


def test_us103_site_update_deactivate_reactivate(client: TestClient, api: Api) -> None:
    t = api.tenant()
    url = f"{API}/sites/{t.sites['S1']}"
    etag = client.get(url, headers=t.admin.headers).headers["ETag"]
    upd = client.patch(
        url,
        headers={**t.admin.headers, "If-Match": etag},
        json={"name": "Mine Nord", "timezone": "Africa/Lagos"},
    )
    assert upd.status_code == 200 and upd.json()["timezone"] == "Africa/Lagos"
    off = client.post(f"{url}/deactivate", headers={**t.admin.headers, "If-Match": upd.headers["ETag"]})
    assert off.status_code == 200 and off.json()["status"] == "INACTIVE"
    again = client.post(f"{url}/deactivate", headers={**t.admin.headers, "If-Match": off.headers["ETag"]})
    assert again.status_code == 409 and again.json()["code"] == "STATE_TRANSITION_INVALID"
    on = client.post(f"{url}/reactivate", headers={**t.admin.headers, "If-Match": off.headers["ETag"]})
    assert on.status_code == 200 and on.json()["status"] == "ACTIVE"


def test_us127_each_write_produces_exactly_one_business_event(client: TestClient, api: Api) -> None:
    t = api.tenant()
    created = client.post(
        f"{API}/sites", headers=t.admin.headers, json={"code": "AU", "name": "Audit", "site_type": "MINE"}
    )
    site_id = created.json()["site_id"]
    events = client.get(f"{API}/audit-events", headers=t.admin.headers, params={"entity_id": site_id}).json()
    assert events["total"] == 1
    event = events["items"][0]
    assert (event["action"], event["actor_user_id"], event["outcome"]) == (
        "site.create",
        str(t.admin.user_id),
        "SUCCESS",
    )
    assert event["request_id"] == created.headers["X-Request-ID"]


def test_us127_a3_failed_write_leaves_no_trace(client: TestClient, api: Api) -> None:
    t = api.tenant()
    before = client.get(f"{API}/audit-events", headers=t.admin.headers).json()["total"]
    resp = client.post(
        f"{API}/sites", headers=t.admin.headers, json={"code": "S1", "name": "Doublon", "site_type": "MINE"}
    )
    assert resp.status_code == 409
    assert client.get(f"{API}/audit-events", headers=t.admin.headers).json()["total"] == before


def test_us126_audit_readable_by_admin_and_auditor_only(client: TestClient, api: Api) -> None:
    t = api.tenant()
    auditor = api.user(t, "AUDITOR")
    assert client.get(f"{API}/audit-events", headers=auditor.headers).status_code == 200
    for role in ("HR", "DIRECTION"):
        viewer = api.user(t, role)
        assert client.get(f"{API}/audit-events", headers=viewer.headers).status_code == 403
    missing = client.get(f"{API}/audit-events/{uuid.uuid4()}", headers=t.admin.headers)
    assert missing.status_code == 404


def test_us126_no_write_route_on_audit(client: TestClient, api: Api) -> None:
    t = api.tenant()
    event_id = client.get(f"{API}/audit-events", headers=t.admin.headers).json()["items"][0]["audit_event_id"]
    for method in ("PATCH", "PUT", "DELETE"):
        resp = client.request(method, f"{API}/audit-events/{event_id}", headers=t.admin.headers)
        assert resp.status_code == 405


def test_us126_a7_no_secret_or_personal_value_in_audit(client: TestClient, api: Api) -> None:
    t = api.tenant()
    client.post(
        f"{API}/users",
        headers=t.admin.headers,
        json={
            "email": f"s.{uuid.uuid4().hex[:6]}@example.com",
            "display_name": "Nom-Test S",
            "phone": "+224000000777",
            "role_code": "HR",
            "scope_type": "TENANT",
        },
    )
    raw = client.get(f"{API}/audit-events", headers=t.admin.headers, params={"page_size": 200}).text
    assert "+224000000777" not in raw and "@example.com" not in raw and "argon2" not in raw
    assert PASSWORD not in raw


def test_d23_tenant_timezone_update(client: TestClient, api: Api) -> None:
    t = api.tenant()
    etag = client.get(f"{API}/tenant", headers=t.admin.headers).headers["ETag"]
    resp = client.patch(
        f"{API}/tenant",
        headers={**t.admin.headers, "If-Match": etag},
        json={"default_timezone": "Africa/Lagos"},
    )
    assert resp.status_code == 200 and resp.json()["default_timezone"] == "Africa/Lagos"
