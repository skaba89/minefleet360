"""US-1.05, US-1.08, US-1.09, US-1.10, US-1.02 (effet sur les sessions) — authentification."""

import uuid

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.email import MemoryEmailSender
from tests.conftest import API, PASSWORD, Api, bearer, last_token


def _login(client: TestClient, code: str, email: str, password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return client.post(
        f"{API}/auth/login", json={"workspace_code": code, "email": email, "password": password}
    )


def _strip(body: dict) -> dict:  # type: ignore[type-arg]
    return {k: v for k, v in body.items() if k != "request_id"}


def test_login_success_sets_httponly_refresh_cookie(client: TestClient, api: Api) -> None:
    t = api.tenant()
    resp = _login(client, t.code, t.admin.email)
    assert resp.status_code == 200
    cookie = resp.headers["set-cookie"]
    assert "mf_refresh=" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Path=/api/v1/auth" in cookie
    assert client.get(f"{API}/me", headers=bearer(resp.json()["access_token"])).status_code == 200


def test_us108_a2_identical_401_for_all_failure_causes(client: TestClient, api: Api) -> None:
    t = api.tenant()
    invited = api.user(t, "HR", activate=False)
    disabled = api.user(t, "HR")
    version = client.get(f"{API}/users/{disabled.user_id}", headers=t.admin.headers).headers["ETag"]
    assert (
        client.post(
            f"{API}/users/{disabled.user_id}/deactivate", headers={**t.admin.headers, "If-Match": version}
        ).status_code
        == 200
    )
    suspended = api.tenant()

    cases = [
        _login(client, "code-inconnu-x", t.admin.email),
        _login(client, t.code, "inconnu@example.com"),
        _login(client, t.code, t.admin.email, "mauvais-mot-de-passe"),
        _login(client, t.code, invited.email),
        _login(client, t.code, disabled.email),
    ]
    platform = api.platform()
    etag = client.get(f"{API}/platform/tenants/{suspended.tenant_id}", headers=platform).headers["ETag"]
    assert (
        client.post(
            f"{API}/platform/tenants/{suspended.tenant_id}/suspend",
            headers={**platform, "If-Match": etag},
            json={"reason": "Test de suspension"},
        ).status_code
        == 200
    )
    cases.append(_login(client, suspended.code, suspended.admin.email))
    # Le code du tenant plateforme n'est pas accepté sur l'entrée tenant.
    cases.append(_login(client, get_settings().platform_tenant_code, "plateforme@example.com"))

    assert [r.status_code for r in cases] == [401] * len(cases)
    bodies = {str(_strip(r.json())) for r in cases}
    assert len(bodies) == 1 and "INVALID_CREDENTIALS" in bodies.pop()


def test_us102_suspension_revokes_existing_sessions(client: TestClient, api: Api) -> None:
    t = api.tenant()
    assert client.get(f"{API}/tenant", headers=t.admin.headers).status_code == 200
    platform = api.platform()
    etag = client.get(f"{API}/platform/tenants/{t.tenant_id}", headers=platform).headers["ETag"]
    resp = client.post(
        f"{API}/platform/tenants/{t.tenant_id}/suspend",
        headers={**platform, "If-Match": etag},
        json={"reason": "Impayé fictif"},
    )
    assert resp.status_code == 200 and resp.json()["status"] == "SUSPENDED"
    after = client.get(f"{API}/tenant", headers=t.admin.headers)
    assert after.status_code == 401 and after.json()["code"] == "AUTH_REQUIRED"

    etag = client.get(f"{API}/platform/tenants/{t.tenant_id}", headers=platform).headers["ETag"]
    assert (
        client.post(
            f"{API}/platform/tenants/{t.tenant_id}/reactivate",
            headers={**platform, "If-Match": etag},
            json={"reason": "Régularisé"},
        ).status_code
        == 200
    )
    assert _login(client, t.code, t.admin.email).status_code == 200


def test_us108_a3_rate_limited_after_max_failures(client: TestClient, api: Api) -> None:
    t = api.tenant()
    settings = get_settings()
    for _ in range(settings.login_max_failures):
        assert _login(client, t.code, t.admin.email, "faux-mot-de-passe").status_code == 401
    blocked = _login(client, t.code, t.admin.email)
    assert blocked.status_code == 429 and blocked.json()["code"] == "RATE_LIMITED"
    assert "retry-after" in blocked.headers


def test_us108_a4_same_email_in_two_tenants_opens_the_right_tenant(client: TestClient, api: Api) -> None:
    a, b = api.tenant(), api.tenant()
    shared = f"partage.{uuid.uuid4().hex[:6]}@example.com"
    for tenant in (a, b):
        resp = client.post(
            f"{API}/users",
            headers=tenant.admin.headers,
            json={
                "email": shared,
                "display_name": "Nom-Test Partagé",
                "role_code": "HR",
                "scope_type": "TENANT",
            },
        )
        assert resp.status_code == 201, resp.text
        api.activate(shared)
    me = client.get(f"{API}/me", headers=api.login(a.code, shared)).json()
    assert me["workspace_code"] == a.code


def test_refresh_rotates_and_reuse_revokes_session(client: TestClient, api: Api) -> None:
    t = api.tenant()
    first = _login(client, t.code, t.admin.email)
    old_cookie = first.cookies["mf_refresh"]
    client.cookies.clear()
    rotated = client.post(f"{API}/auth/refresh", cookies={"mf_refresh": old_cookie})
    assert rotated.status_code == 200
    new_cookie = rotated.cookies["mf_refresh"]
    assert new_cookie != old_cookie
    client.cookies.clear()

    # Rejeu de l'ancien refresh hors fenêtre de grâce : on simule en vidant la fenêtre.
    settings = get_settings()
    grace = settings.refresh_grace_period
    settings.refresh_grace_period = grace * 0
    try:
        replay = client.post(f"{API}/auth/refresh", cookies={"mf_refresh": old_cookie})
    finally:
        settings.refresh_grace_period = grace
    client.cookies.clear()
    assert replay.status_code == 401
    # La session entière est révoquée : le refresh légitime et le jeton d'accès ne marchent plus.
    assert client.post(f"{API}/auth/refresh", cookies={"mf_refresh": new_cookie}).status_code == 401
    client.cookies.clear()
    assert client.get(f"{API}/me", headers=bearer(rotated.json()["access_token"])).status_code == 401


def test_refresh_rejects_foreign_origin(client: TestClient, api: Api) -> None:
    t = api.tenant()
    cookie = _login(client, t.code, t.admin.email).cookies["mf_refresh"]
    client.cookies.clear()
    resp = client.post(
        f"{API}/auth/refresh", cookies={"mf_refresh": cookie}, headers={"Origin": "https://evil.example"}
    )
    client.cookies.clear()
    assert resp.status_code == 401


def test_us109_logout_revokes_session_and_is_idempotent(client: TestClient, api: Api) -> None:
    t = api.tenant()
    resp = _login(client, t.code, t.admin.email)
    access, cookie = resp.json()["access_token"], resp.cookies["mf_refresh"]
    client.cookies.clear()
    assert client.post(f"{API}/auth/logout", cookies={"mf_refresh": cookie}).status_code == 204
    client.cookies.clear()
    assert client.get(f"{API}/me", headers=bearer(access)).status_code == 401
    assert client.post(f"{API}/auth/logout", cookies={"mf_refresh": cookie}).status_code == 204
    client.cookies.clear()
    assert client.post(f"{API}/auth/logout").status_code == 204


def test_us105_invitation_token_single_use_and_invalid_cases(
    client: TestClient, api: Api, outbox: MemoryEmailSender
) -> None:
    t = api.tenant()
    invited = api.user(t, "HR", activate=False)
    token = last_token(outbox, invited.email)
    weak = client.post(f"{API}/auth/invitations/accept", json={"token": token, "password": "court"})
    assert weak.status_code == 422 and weak.json()["code"] == "PASSWORD_POLICY_VIOLATION"
    ok = client.post(f"{API}/auth/invitations/accept", json={"token": token, "password": PASSWORD})
    assert ok.status_code == 204
    reused = client.post(f"{API}/auth/invitations/accept", json={"token": token, "password": PASSWORD})
    tampered = client.post(
        f"{API}/auth/invitations/accept", json={"token": token[:-4] + "AAAA", "password": PASSWORD}
    )
    foreign_tenant = token.replace(str(t.tenant_id), str(uuid.uuid4()))
    other = client.post(
        f"{API}/auth/invitations/accept", json={"token": foreign_tenant, "password": PASSWORD}
    )
    for resp in (reused, tampered, other):
        assert resp.status_code == 422 and resp.json()["code"] == "TOKEN_INVALID"


def test_us110_password_reset_flow_revokes_sessions(
    client: TestClient, api: Api, outbox: MemoryEmailSender
) -> None:
    t = api.tenant()
    hr = api.user(t, "HR")
    unknown = client.post(
        f"{API}/auth/password/reset-request", json={"workspace_code": t.code, "email": "absent@example.com"}
    )
    known = client.post(
        f"{API}/auth/password/reset-request", json={"workspace_code": t.code, "email": hr.email}
    )
    assert unknown.status_code == known.status_code == 202
    assert _strip(unknown.json()) == _strip(known.json())

    token = last_token(outbox, hr.email)
    new_password = "Nouveau-mot-de-passe-fictif-9"
    assert (
        client.post(
            f"{API}/auth/password/reset-confirm", json={"token": token, "password": new_password}
        ).status_code
        == 204
    )
    assert client.get(f"{API}/me", headers=hr.headers).status_code == 401
    assert _login(client, t.code, hr.email, new_password).status_code == 200
    again = client.post(f"{API}/auth/password/reset-confirm", json={"token": token, "password": new_password})
    assert again.json()["code"] == "TOKEN_INVALID"


def test_change_own_password_keeps_current_session_only(client: TestClient, api: Api) -> None:
    t = api.tenant()
    other_session = api.login(t.code, t.admin.email)
    resp = client.post(
        f"{API}/me/password",
        headers=t.admin.headers,
        json={"current_password": PASSWORD, "new_password": "Autre-mot-de-passe-fictif-7"},
    )
    assert resp.status_code == 204
    assert client.get(f"{API}/me", headers=t.admin.headers).status_code == 200
    assert client.get(f"{API}/me", headers=other_session).status_code == 401


def test_expired_or_forged_access_token_is_401(client: TestClient) -> None:
    for header in ({}, bearer("abc.def.ghi"), {"Authorization": "Basic xyz"}):
        resp = client.get(f"{API}/me", headers=header)
        assert resp.status_code == 401 and resp.json()["code"] == "AUTH_REQUIRED"
