"""R3 : rejeu de tous les refresh consommés, bornage, compatibilité et isolation."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.db import new_session
from app.core.security import CompositeToken, parse_composite_token, sha256
from app.core.tenancy import set_tenant_context
from app.identity.models import AuthSession
from tests.conftest import API, PASSWORD, Api, bearer


def _login(client: TestClient, code: str, email: str):  # type: ignore[no-untyped-def]
    return client.post(
        f"{API}/auth/login", json={"workspace_code": code, "email": email, "password": PASSWORD}
    )


def _refresh(client: TestClient, cookie: str):  # type: ignore[no-untyped-def]
    client.cookies.clear()
    response = client.post(f"{API}/auth/refresh", cookies={"mf_refresh": cookie})
    client.cookies.clear()
    return response


def _session_cookie(cookie: str) -> CompositeToken:
    token = parse_composite_token(cookie)
    assert token is not None
    return token


def test_oldest_consumed_refresh_revokes_session_after_multiple_rotations(
    client: TestClient, api: Api
) -> None:
    tenant = api.tenant()
    initial = _login(client, tenant.code, tenant.admin.email)
    original_cookie = initial.cookies["mf_refresh"]
    first = _refresh(client, original_cookie)
    assert first.status_code == 200
    second = _refresh(client, first.cookies["mf_refresh"])
    assert second.status_code == 200

    # T0 est plus ancien que previous=T1 : aucune grâce ne s'applique, même immédiatement.
    replay = _refresh(client, original_cookie)
    assert replay.status_code == 401
    assert _refresh(client, second.cookies["mf_refresh"]).status_code == 401
    assert client.get(f"{API}/me", headers=bearer(second.json()["access_token"])).status_code == 401
    token = _session_cookie(original_cookie)
    events = client.get(
        f"{API}/audit-events",
        headers=tenant.admin.headers,
        params={"entity_id": str(token.record_id)},
    ).json()["items"]
    reused = [event for event in events if event["action"] == "auth.refresh_reuse"]
    assert len(reused) == 1 and reused[0]["reason"] == "REFRESH_REUSE"
    assert original_cookie not in str(reused) and token.secret not in str(reused)


def test_immediately_previous_refresh_in_grace_is_rejected_without_revoking_session(
    client: TestClient, api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "refresh_grace_period", timedelta(minutes=5))
    tenant = api.tenant()
    initial = _login(client, tenant.code, tenant.admin.email).cookies["mf_refresh"]
    first = _refresh(client, initial)
    assert first.status_code == 200
    assert _refresh(client, initial).status_code == 401
    assert _refresh(client, first.cookies["mf_refresh"]).status_code == 200


def test_legacy_previous_hash_is_preserved_at_next_rotation(client: TestClient, api: Api) -> None:
    tenant = api.tenant()
    initial = _login(client, tenant.code, tenant.admin.email).cookies["mf_refresh"]
    first = _refresh(client, initial)
    assert first.status_code == 200
    token = _session_cookie(initial)
    # Une session qui existait avant 0009 conserve previous mais n'a pas encore d'historique.
    with new_session() as db:
        set_tenant_context(db, token.tenant_id)
        session = db.execute(
            select(AuthSession).where(AuthSession.auth_session_id == token.record_id)
        ).scalar_one()
        session.consumed_refresh_hashes = []
        db.commit()
    second = _refresh(client, first.cookies["mf_refresh"])
    assert second.status_code == 200
    assert _refresh(client, initial).status_code == 401
    assert _refresh(client, second.cookies["mf_refresh"]).status_code == 401


def test_forged_tenant_cookie_cannot_read_or_revoke_foreign_session(client: TestClient, api: Api) -> None:
    tenant, other = api.tenant(), api.tenant()
    initial = _login(client, tenant.code, tenant.admin.email).cookies["mf_refresh"]
    token = _session_cookie(initial)
    forged = CompositeToken(other.tenant_id, token.record_id, token.secret).encode()
    assert _refresh(client, forged).status_code == 401
    assert _refresh(client, initial).status_code == 200


def test_unknown_refresh_secret_does_not_revoke_session(client: TestClient, api: Api) -> None:
    tenant = api.tenant()
    initial = _login(client, tenant.code, tenant.admin.email).cookies["mf_refresh"]
    token = _session_cookie(initial)
    forged = CompositeToken(token.tenant_id, token.record_id, "unknown-synthetic-secret").encode()
    assert _refresh(client, forged).status_code == 401
    assert _refresh(client, initial).status_code == 200


def test_refresh_refuses_account_marked_mfa_after_login(client: TestClient, api: Api) -> None:
    tenant = api.tenant()
    cookie = _login(client, tenant.code, tenant.admin.email).cookies["mf_refresh"]
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        db.execute(
            text(
                "UPDATE user_account SET mfa_enabled = true,"
                " mfa_secret_encrypted = decode('00', 'hex')"
                " WHERE user_account_id = :user_id"
            ),
            {"user_id": tenant.admin.user_id},
        )
        db.commit()
    assert _refresh(client, cookie).status_code == 401


def test_rotation_limit_revokes_instead_of_dropping_consumed_hashes(client: TestClient, api: Api) -> None:
    tenant = api.tenant()
    login = _login(client, tenant.code, tenant.admin.email)
    cookie = login.cookies["mf_refresh"]
    token = _session_cookie(cookie)
    history = [sha256(f"synthetic-consumed-refresh-{index}") for index in range(1024)]
    with new_session() as db:
        set_tenant_context(db, token.tenant_id)
        session = db.execute(
            select(AuthSession).where(AuthSession.auth_session_id == token.record_id)
        ).scalar_one()
        session.consumed_refresh_hashes = history
        db.commit()

    assert _refresh(client, cookie).status_code == 401
    assert client.get(f"{API}/me", headers=bearer(login.json()["access_token"])).status_code == 401
    with new_session() as db:
        set_tenant_context(db, token.tenant_id)
        session = db.get(AuthSession, token.record_id)
        assert session is not None
        assert session.revoked_reason == "REFRESH_ROTATION_LIMIT"
        assert session.consumed_refresh_hashes == history
    events = client.get(
        f"{API}/audit-events",
        headers=tenant.admin.headers,
        params={"entity_id": str(token.record_id)},
    ).json()["items"]
    assert sum(event["action"] == "auth.refresh_limit" for event in events) == 1


def test_logout_accepts_an_old_consumed_refresh(client: TestClient, api: Api) -> None:
    tenant = api.tenant()
    initial = _login(client, tenant.code, tenant.admin.email).cookies["mf_refresh"]
    first = _refresh(client, initial)
    second = _refresh(client, first.cookies["mf_refresh"])
    client.cookies.clear()
    logout = client.post(f"{API}/auth/logout", cookies={"mf_refresh": initial})
    client.cookies.clear()
    assert logout.status_code == 204
    assert _refresh(client, second.cookies["mf_refresh"]).status_code == 401
