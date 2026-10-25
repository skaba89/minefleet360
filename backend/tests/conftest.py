"""Harnais de test : PostgreSQL réel (base minefleet_test), migrations rejouées, rôle applicatif mf_app.

Aucune donnée n'est supprimée entre les tests (mf_app n'a pas DELETE) : chaque test crée ses propres
tenants fictifs, avec des codes uniques. Le PLATFORM_ADMIN est unique pour la session de test.
"""

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from app.core.db import dispose_engine
from app.core.email import MemoryEmailSender

PLATFORM_EMAIL = "plateforme@example.com"
PASSWORD = "Mot-de-passe-fictif-2026"
API = "/api/v1"


def _require_test_database() -> None:
    settings = get_settings()
    if settings.env != "test" or not settings.db_name.endswith("_test"):
        pytest.exit("Les tests exigent MF_ENV=test et une base *_test (scripts/test.ps1).", returncode=2)


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    _require_test_database()
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    dispose_engine()
    from app.cli import create_platform_admin

    assert create_platform_admin(PLATFORM_EMAIL, "Admin Plateforme Fictif", PASSWORD) == 0
    yield
    dispose_engine()


@pytest.fixture(scope="session")
def outbox() -> MemoryEmailSender:
    return MemoryEmailSender()


@pytest.fixture(scope="session")
def client(database: None, outbox: MemoryEmailSender) -> Iterator[TestClient]:
    from app.main import create_app

    app = create_app(email_sender=outbox)
    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _reset_rate_limits(client: TestClient) -> None:
    limiters = client.app.state.auth_limiters  # type: ignore[attr-defined]
    limiters.login.clear()
    limiters.source.clear()
    limiters.tokens.clear()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def unique_code(prefix: str = "t") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def last_token(outbox: MemoryEmailSender, email: str) -> str:
    for message in reversed(outbox.outbox):
        if message.to.lower() == email.lower():
            return message.body.split("#token=")[1].split()[0]
    raise AssertionError(f"aucun message pour {email}")


@dataclass
class Account:
    user_id: uuid.UUID
    email: str
    headers: dict[str, str]


@dataclass
class TenantFixture:
    tenant_id: uuid.UUID
    code: str
    admin: Account
    sites: dict[str, uuid.UUID] = field(default_factory=dict)
    users: dict[str, Account] = field(default_factory=dict)


class Api:
    """Fabrique de données fictives passant par l'API (audit et invariants réellement exercés)."""

    def __init__(self, client: TestClient, outbox: MemoryEmailSender) -> None:
        self.client = client
        self.outbox = outbox
        self._platform: dict[str, str] | None = None

    def login(self, code: str, email: str, password: str = PASSWORD) -> dict[str, str]:
        resp = self.client.post(
            f"{API}/auth/login", json={"workspace_code": code, "email": email, "password": password}
        )
        assert resp.status_code == 200, resp.text
        return bearer(resp.json()["access_token"])

    def platform(self) -> dict[str, str]:
        if self._platform is None:
            resp = self.client.post(
                f"{API}/auth/platform/login", json={"email": PLATFORM_EMAIL, "password": PASSWORD}
            )
            assert resp.status_code == 200, resp.text
            self._platform = bearer(resp.json()["access_token"])
        return self._platform

    def activate(self, email: str) -> None:
        resp = self.client.post(
            f"{API}/auth/invitations/accept",
            json={"token": last_token(self.outbox, email), "password": PASSWORD},
        )
        assert resp.status_code == 204, resp.text

    def tenant(self, *, sites: tuple[str, ...] = ("S1", "S2")) -> TenantFixture:
        code = unique_code()
        admin_email = f"admin.{code}@example.com"
        resp = self.client.post(
            f"{API}/platform/tenants",
            headers=self.platform(),
            json={
                "code": code,
                "legal_name": f"Société fictive {code}",
                "display_name": f"Fictive {code}",
                "admin_email": admin_email,
                "admin_display_name": "Admin Fictif",
            },
        )
        assert resp.status_code == 201, resp.text
        self.activate(admin_email)
        headers = self.login(code, admin_email)
        me = self.client.get(f"{API}/me", headers=headers).json()
        fixture = TenantFixture(
            tenant_id=uuid.UUID(resp.json()["tenant_id"]),
            code=code,
            admin=Account(uuid.UUID(me["user_account_id"]), admin_email, headers),
        )
        for site_code in sites:
            created = self.client.post(
                f"{API}/sites",
                headers=headers,
                json={"code": site_code, "name": f"Site {site_code}", "site_type": "MINE"},
            )
            assert created.status_code == 201, created.text
            fixture.sites[site_code] = uuid.UUID(created.json()["site_id"])
        return fixture

    def user(
        self,
        tenant: TenantFixture,
        role: str,
        scope: str = "TENANT",
        site: str | None = None,
        *,
        activate: bool = True,
    ) -> Account:
        email = f"{role.lower()}.{uuid.uuid4().hex[:8]}@example.com"
        body: dict[str, object] = {
            "email": email,
            "display_name": f"Nom-Test {role}",
            "role_code": role,
            "scope_type": scope,
        }
        if site is not None:
            body["site_id"] = str(tenant.sites[site])
        resp = self.client.post(f"{API}/users", headers=tenant.admin.headers, json=body)
        assert resp.status_code == 201, resp.text
        user_id = uuid.UUID(resp.json()["user_account_id"])
        headers: dict[str, str] = {}
        if activate:
            self.activate(email)
            headers = self.login(tenant.code, email)
        return Account(user_id, email, headers)


@pytest.fixture(scope="session")
def api(client: TestClient, outbox: MemoryEmailSender) -> Api:
    return Api(client, outbox)
