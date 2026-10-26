"""R3 : limites partagées, transactions indépendantes, bornage et refus MFA explicite."""

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from app.core.config import get_settings
from app.core.db import new_session
from app.core.email import MemoryEmailSender
from app.core.ratelimit import FailureLimiter
from app.core.tenancy import set_tenant_context
from tests.conftest import API, PASSWORD, Api


def test_auth_limits_survive_another_app_instance(client: TestClient, api: Api) -> None:
    from app.main import create_app

    tenant = api.tenant()
    with TestClient(create_app(email_sender=MemoryEmailSender())) as second:
        for index in range(get_settings().login_max_failures):
            target = client if index % 2 else second
            result = target.post(
                f"{API}/auth/login",
                json={"workspace_code": tenant.code, "email": tenant.admin.email, "password": "faux"},
            )
            assert result.status_code == 401
    # Une nouvelle application ne retrouve aucun état mémoire; PostgreSQL garde les échecs.
    with TestClient(create_app(email_sender=MemoryEmailSender())) as restarted:
        result = restarted.post(
            f"{API}/auth/login",
            json={"workspace_code": tenant.code, "email": tenant.admin.email, "password": PASSWORD},
        )
        assert (result.status_code, result.json()["code"]) == (429, "RATE_LIMITED")


def test_shared_limiter_atomic_records_and_expiry() -> None:
    now = datetime.now(UTC)
    key = f"synthetic-{uuid.uuid4()}"
    limit = FailureLimiter("login", 20, timedelta(minutes=1))
    with ThreadPoolExecutor(max_workers=4) as workers:
        list(workers.map(lambda _: limit.record_failure(key, now), range(20)))
    other = FailureLimiter("login", 20, timedelta(minutes=1))
    assert other.is_blocked(key, now)
    # Une date applicative future ne doit pas permettre d'avancer l'horloge du stockage partagé.
    assert other.is_blocked(key, now + timedelta(days=1))
    owner = create_engine(get_settings().database_url(owner=True), hide_parameters=True)
    try:
        with owner.begin() as connection:
            connection.execute(
                text(
                    "UPDATE app.auth_failure_bucket"
                    " SET failures = ARRAY[clock_timestamp()-interval '2 minutes'],"
                    " expires_at = clock_timestamp()-interval '1 minute' WHERE namespace = 'login'"
                )
            )
        assert not other.is_blocked(key, now)
    finally:
        owner.dispose()
    other.reset(key)
    assert not limit.is_blocked(key, now)


def test_reads_do_not_allocate_and_storage_contains_only_hmac_keys() -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    limiter = FailureLimiter("login", 5, timedelta(seconds=60))
    owner = create_engine(settings.database_url(owner=True), hide_parameters=True)
    try:
        for index in range(25):
            assert not limiter.is_blocked(f"fictif-{index}@example.com", now)
        with owner.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM app.auth_failure_bucket")).scalar_one() == 0
        limiter.record_failure("fictif@example.com:192.0.2.1", now)
        with owner.connect() as connection:
            key_hash, size = connection.execute(
                text("SELECT key_hash, cardinality(failures) FROM app.auth_failure_bucket")
            ).one()
            assert len(key_hash) == 64 and all(char in "0123456789abcdef" for char in key_hash)
            assert "fictif" not in key_hash and size == 1
        with owner.begin() as connection:
            connection.execute(
                text(
                    "UPDATE app.auth_failure_bucket"
                    " SET failures = ARRAY[clock_timestamp()-interval '2 minutes'],"
                    " expires_at = clock_timestamp()-interval '1 minute'"
                )
            )
        limiter.record_failure("other-synthetic", now)
        with owner.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM app.auth_failure_bucket")).scalar_one() == 1
    finally:
        owner.dispose()


def test_limiter_capacity_fails_closed_without_growing() -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    owner = create_engine(settings.database_url(owner=True), hide_parameters=True)
    try:
        with owner.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO app.auth_failure_bucket(namespace, key_hash, failures, expires_at)"
                    " SELECT 'login', md5(n::text) || md5(n::text), ARRAY[:instant]::timestamptz[],"
                    " :instant + interval '1 minute' FROM generate_series(1, 10000) n"
                ),
                {"instant": now},
            )
        limiter = FailureLimiter("login", 5, timedelta(seconds=60))
        assert limiter.is_blocked("new-synthetic-key", now)
        limiter.record_failure("new-synthetic-key", now)
        with owner.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM app.auth_failure_bucket")).scalar_one() == 10000
            )
        with owner.begin() as connection:
            connection.execute(
                text(
                    "UPDATE app.auth_failure_bucket"
                    " SET failures = ARRAY[clock_timestamp()-interval '2 minutes'],"
                    " expires_at = clock_timestamp()-interval '1 minute'"
                )
            )
        limiter.record_failure("new-synthetic-key", now)
        assert not limiter.is_blocked("new-synthetic-key", now)
        with owner.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM app.auth_failure_bucket")).scalar_one() == 1
    finally:
        owner.dispose()


def test_app_role_cannot_read_or_clear_global_limits() -> None:
    with new_session() as db:
        with pytest.raises(ProgrammingError) as exc:
            db.execute(text("SELECT * FROM app.auth_failure_bucket"))
        assert exc.value.orig is not None and exc.value.orig.sqlstate == "42501"
        db.rollback()
        with pytest.raises(ProgrammingError) as exc:
            db.execute(text("DELETE FROM app.auth_failure_bucket"))
        assert exc.value.orig is not None and exc.value.orig.sqlstate == "42501"


def test_mfa_flag_refuses_password_login_existing_access_and_refresh(client: TestClient, api: Api) -> None:
    tenant = api.tenant()
    current = client.post(
        f"{API}/auth/login",
        json={"workspace_code": tenant.code, "email": tenant.admin.email, "password": PASSWORD},
    )
    cookie = current.cookies["mf_refresh"]
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        db.execute(
            text(
                "UPDATE user_account SET mfa_enabled = true, mfa_secret_encrypted = :secret"
                " WHERE user_account_id = :user_id"
            ),
            {"secret": b"synthetic-encrypted-placeholder", "user_id": tenant.admin.user_id},
        )
        db.commit()
    refused = client.post(
        f"{API}/auth/login",
        json={"workspace_code": tenant.code, "email": tenant.admin.email, "password": PASSWORD},
    )
    assert refused.status_code == 401 and refused.json()["code"] == "INVALID_CREDENTIALS"
    assert "set-cookie" not in refused.headers
    assert client.get(f"{API}/tenant", headers=tenant.admin.headers).status_code == 401
    client.cookies.clear()
    assert client.post(f"{API}/auth/refresh", cookies={"mf_refresh": cookie}).status_code == 401
    client.cookies.clear()


def test_reset_mail_failure_does_not_disclose_account(
    client: TestClient, api: Api, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    tenant = api.tenant()

    class FailingSender:
        def send(self, message: object) -> None:
            del message
            raise RuntimeError("synthetic-secret recipient-fictif@example.com")

    monkeypatch.setattr(client.app.state, "email_sender", FailingSender())
    with caplog.at_level(logging.ERROR, logger="minefleet.security"):
        known = client.post(
            f"{API}/auth/password/reset-request",
            json={
                "workspace_code": tenant.code,
                "email": tenant.admin.email,
            },
        )
        unknown = client.post(
            f"{API}/auth/password/reset-request",
            json={
                "workspace_code": tenant.code,
                "email": "unknown-synthetic@example.com",
            },
        )
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert "email_delivery_failed" in caplog.text
    assert "synthetic-secret" not in caplog.text and "recipient-fictif@example.com" not in caplog.text
