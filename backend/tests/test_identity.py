"""US-1.04, US-1.06, US-1.07, US-1.31 — utilisateurs, rôles, protections anti-escalade."""

import threading
import uuid

from fastapi.testclient import TestClient

from app.core.email import MemoryEmailSender
from tests.conftest import API, PASSWORD, Api, TenantFixture, last_token


def _etag(client: TestClient, url: str, headers: dict[str, str]) -> str:
    resp = client.get(url, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.headers["ETag"]


def _assignments(client: TestClient, t: TenantFixture, user_id: uuid.UUID) -> list[dict]:  # type: ignore[type-arg]
    resp = client.get(f"{API}/role-assignments", headers=t.admin.headers, params={"user_id": str(user_id)})
    return resp.json()["items"]  # type: ignore[no-any-return]


def _revoke(client: TestClient, headers: dict[str, str], assignment: dict):  # type: ignore[no-untyped-def,type-arg]
    return client.post(
        f"{API}/role-assignments/{assignment['user_role_assignment_id']}/revoke",
        headers={**headers, "If-Match": f'"{assignment["row_version"]}"'},
    )


def _security_events(client: TestClient, t: TenantFixture, reason: str) -> list[dict]:  # type: ignore[type-arg]
    items = client.get(f"{API}/audit-events", headers=t.admin.headers, params={"page_size": 200}).json()[
        "items"
    ]
    return [e for e in items if e["outcome"] == "DENIED" and e["reason"] == reason]


def test_us104_invite_creates_invited_account_and_audits(client: TestClient, api: Api) -> None:
    t = api.tenant()
    hr = api.user(t, "HR", activate=False)
    user = client.get(f"{API}/users/{hr.user_id}", headers=t.admin.headers).json()
    assert user["status"] == "INVITED"
    events = client.get(
        f"{API}/audit-events", headers=t.admin.headers, params={"entity_id": str(hr.user_id)}
    ).json()["items"]
    assert [e["action"] for e in events] == ["user.invite"]
    assert "email" not in (events[0]["after_data"] or {}) and "email" in events[0]["changed_fields"]


def test_us104_duplicate_email_same_tenant_is_409_case_insensitive(client: TestClient, api: Api) -> None:
    t = api.tenant()
    hr = api.user(t, "HR", activate=False)
    resp = client.post(
        f"{API}/users",
        headers=t.admin.headers,
        json={
            "email": hr.email.upper(),
            "display_name": "Nom-Test",
            "role_code": "HR",
            "scope_type": "TENANT",
        },
    )
    assert resp.status_code == 409 and resp.json()["code"] == "DUPLICATE_EMAIL"


def test_us104_role_and_scope_rules(client: TestClient, api: Api) -> None:
    t = api.tenant()

    def invite(**extra: object):  # type: ignore[no-untyped-def]
        body = {"email": f"u.{uuid.uuid4().hex[:6]}@example.com", "display_name": "Nom-Test", **extra}
        return client.post(f"{API}/users", headers=t.admin.headers, json=body)

    platform = invite(role_code="PLATFORM_ADMIN", scope_type="PLATFORM")
    unknown = invite(role_code="ROI_DU_MONDE", scope_type="TENANT")
    dispatcher_tenant = invite(role_code="DISPATCHER", scope_type="TENANT")
    site_without_id = invite(role_code="OPS_MANAGER", scope_type="SITE")
    assert (platform.status_code, platform.json()["code"]) == (422, "ROLE_NOT_ASSIGNABLE")
    assert (unknown.status_code, unknown.json()["code"]) == (422, "ROLE_NOT_ASSIGNABLE")
    assert (dispatcher_tenant.status_code, dispatcher_tenant.json()["code"]) == (
        422,
        "SCOPE_NOT_ALLOWED_FOR_ROLE",
    )
    assert (site_without_id.status_code, site_without_id.json()["code"]) == (422, "VALIDATION_ERROR")
    assert len(_security_events(client, t, "ROLE_NOT_ASSIGNABLE")) == 2


def test_us106_a8_revoked_role_takes_effect_on_next_request(client: TestClient, api: Api) -> None:
    t = api.tenant()
    hr = api.user(t, "HR")
    assert client.get(f"{API}/users", headers=hr.headers).status_code == 200
    assert _revoke(client, t.admin.headers, _assignments(client, t, hr.user_id)[0]).status_code == 200
    resp = client.get(f"{API}/users", headers=hr.headers)
    assert resp.status_code == 403 and resp.json()["code"] == "PERMISSION_DENIED"


def test_us106_a5_duplicate_assignment_is_409(client: TestClient, api: Api) -> None:
    t = api.tenant()
    hr = api.user(t, "HR")
    resp = client.post(
        f"{API}/role-assignments",
        headers=t.admin.headers,
        json={"user_account_id": str(hr.user_id), "role_code": "HR", "scope_type": "TENANT"},
    )
    assert resp.status_code == 409 and resp.json()["code"] == "DUPLICATE_ROLE_ASSIGNMENT"


def test_us106_a3_grants_are_union_of_assignments(client: TestClient, api: Api) -> None:
    t = api.tenant()
    user = api.user(t, "DISPATCHER", "SITE", "S1")
    assert client.get(f"{API}/users", headers=user.headers).status_code == 403
    assert (
        client.post(
            f"{API}/role-assignments",
            headers=t.admin.headers,
            json={"user_account_id": str(user.user_id), "role_code": "HR", "scope_type": "TENANT"},
        ).status_code
        == 201
    )
    assert client.get(f"{API}/users", headers=user.headers).status_code == 200
    # HR (TENANT) ouvre tous les sites en lecture, en plus de la portée SITE du dispatcher.
    assert client.get(f"{API}/sites", headers=user.headers).json()["total"] == 2


def test_us131_a1_self_role_change_is_422_and_audited(client: TestClient, api: Api) -> None:
    t = api.tenant()
    own = _assignments(client, t, t.admin.user_id)[0]
    add = client.post(
        f"{API}/role-assignments",
        headers=t.admin.headers,
        json={"user_account_id": str(t.admin.user_id), "role_code": "HR", "scope_type": "TENANT"},
    )
    revoke = _revoke(client, t.admin.headers, own)
    for resp in (add, revoke):
        assert resp.status_code == 422 and resp.json()["code"] == "SELF_ROLE_CHANGE_FORBIDDEN"
    assert len(_security_events(client, t, "SELF_ROLE_CHANGE_FORBIDDEN")) == 2


def test_us131_admin_can_remove_another_admin_but_tenant_keeps_one(client: TestClient, api: Api) -> None:
    t = api.tenant()
    second = api.user(t, "TENANT_ADMIN")
    assert _revoke(client, second.headers, _assignments(client, t, t.admin.user_id)[0]).status_code == 200
    # « second » est désormais le seul administrateur : il ne peut ni se retirer ni se désactiver.
    own = next(
        a
        for a in client.get(
            f"{API}/role-assignments", headers=second.headers, params={"user_id": str(second.user_id)}
        ).json()["items"]
        if a["role_code"] == "TENANT_ADMIN"
    )
    assert _revoke(client, second.headers, own).json()["code"] == "SELF_ROLE_CHANGE_FORBIDDEN"
    url = f"{API}/users/{second.user_id}"
    resp = client.post(
        f"{url}/deactivate", headers={**second.headers, "If-Match": _etag(client, url, second.headers)}
    )
    assert resp.json()["code"] == "SELF_ROLE_CHANGE_FORBIDDEN"


def test_us131_a4_concurrent_mutual_revocation_keeps_one_admin(client: TestClient, api: Api) -> None:
    """Le refus 409 LAST_TENANT_ADMIN n'est atteignable qu'en concurrence : c'est ce qu'il protège."""
    t = api.tenant()
    second = api.user(t, "TENANT_ADMIN")
    first_ta = _assignments(client, t, t.admin.user_id)[0]
    second_ta = next(a for a in _assignments(client, t, second.user_id) if a["role_code"] == "TENANT_ADMIN")
    results: dict[str, int] = {}
    barrier = threading.Barrier(2)  # départ simultané des deux révocations (QA1A-07)

    def run(label: str, headers: dict[str, str], assignment: dict) -> None:  # type: ignore[type-arg]
        barrier.wait(timeout=10)
        results[label] = _revoke(client, headers, assignment).status_code

    threads = [
        threading.Thread(target=run, args=("second_revokes_first", second.headers, first_ta)),
        threading.Thread(target=run, args=("first_revokes_second", t.admin.headers, second_ta)),
    ]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert sorted(results.values())[0] == 200 and sorted(results.values())[1] in (403, 409), results
    survivor = second.headers if results["second_revokes_first"] == 200 else t.admin.headers
    remaining = client.get(f"{API}/role-assignments", headers=survivor, params={"page_size": 200}).json()[
        "items"
    ]
    assert sum(1 for a in remaining if a["role_code"] == "TENANT_ADMIN") == 1


def test_us107_deactivation_revokes_sessions_and_reactivation_restores(client: TestClient, api: Api) -> None:
    t = api.tenant()
    hr = api.user(t, "HR")
    url = f"{API}/users/{hr.user_id}"
    resp = client.post(
        f"{url}/deactivate", headers={**t.admin.headers, "If-Match": _etag(client, url, t.admin.headers)}
    )
    assert resp.status_code == 200 and resp.json()["status"] == "DISABLED"
    assert client.get(f"{API}/me", headers=hr.headers).status_code == 401
    resp = client.post(
        f"{url}/reactivate", headers={**t.admin.headers, "If-Match": _etag(client, url, t.admin.headers)}
    )
    assert resp.status_code == 200 and resp.json()["status"] == "ACTIVE"
    assert client.get(f"{API}/users", headers=api.login(t.code, hr.email)).status_code == 200


def test_d15_personal_fields_absent_for_non_admin_roles(client: TestClient, api: Api) -> None:
    t = api.tenant()
    resp = client.post(
        f"{API}/users",
        headers=t.admin.headers,
        json={
            "email": f"tel.{uuid.uuid4().hex[:6]}@example.com",
            "display_name": "Nom-Test Tel",
            "phone": "+224000000123",
            "role_code": "HSE",
            "scope_type": "TENANT",
        },
    )
    user_id = resp.json()["user_account_id"]
    admin_view = client.get(f"{API}/users/{user_id}", headers=t.admin.headers).json()
    assert admin_view["phone"] == "+224000000123" and "email" in admin_view
    for role in ("HR", "AUDITOR"):
        viewer = api.user(t, role)
        raw = client.get(f"{API}/users/{user_id}", headers=viewer.headers).text
        assert "+224000000123" not in raw and '"email"' not in raw and '"phone"' not in raw
        listed = client.get(f"{API}/users", headers=viewer.headers).text
        assert "+224000000123" not in listed and "@example.com" not in listed


def test_ct4_if_match_required_and_stale_version_conflicts(client: TestClient, api: Api) -> None:
    t = api.tenant()
    hr = api.user(t, "HR")
    url = f"{API}/users/{hr.user_id}"
    missing = client.patch(url, headers=t.admin.headers, json={"display_name": "Nom-Test 2"})
    assert missing.status_code == 422 and missing.json()["code"] == "IF_MATCH_REQUIRED"
    etag = _etag(client, url, t.admin.headers)
    ok = client.patch(url, headers={**t.admin.headers, "If-Match": etag}, json={"display_name": "Nom-Test 2"})
    assert ok.status_code == 200 and ok.headers["ETag"] != etag
    stale = client.patch(
        url, headers={**t.admin.headers, "If-Match": etag}, json={"display_name": "Nom-Test 3"}
    )
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"


def test_roles_catalogue_hides_platform_admin_from_tenants(client: TestClient, api: Api) -> None:
    t = api.tenant()
    codes = {r["role_code"] for r in client.get(f"{API}/roles", headers=t.admin.headers).json()}
    assert "PLATFORM_ADMIN" not in codes and {"TENANT_ADMIN", "AUDITOR", "DISPATCHER"} <= codes


def test_deactivation_revokes_pending_invitation_tokens(
    client: TestClient, api: Api, outbox: MemoryEmailSender
) -> None:
    t = api.tenant()
    invited = api.user(t, "HR", activate=False)
    token = last_token(outbox, invited.email)
    url = f"{API}/users/{invited.user_id}"
    for action in ("deactivate", "reactivate"):
        resp = client.post(
            f"{url}/{action}", headers={**t.admin.headers, "If-Match": _etag(client, url, t.admin.headers)}
        )
        assert resp.status_code == 200
    # Réactivé en INVITED : l'ancien lien ne doit pas revivre.
    resp = client.post(f"{API}/auth/invitations/accept", json={"token": token, "password": PASSWORD})
    assert resp.status_code == 422 and resp.json()["code"] == "TOKEN_INVALID"


def test_sec05_site_scoped_hr_cannot_list_accounts(client: TestClient, api: Api) -> None:
    t = api.tenant()
    hr_site = api.user(t, "HR", "SITE", "S1")
    assert client.get(f"{API}/users", headers=hr_site.headers).status_code == 403
