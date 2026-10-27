"""Double authentification TOTP (C-03, SEC-04) : enrôlement doux, connexion en deux étapes, secours."""

import base64
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core import totp
from app.core.clock import SystemClock
from app.core.config import get_settings
from tests.conftest import API, PASSWORD, Account, Api, TenantFixture, bearer


class OffsetClock:
    def __init__(self, offset: timedelta) -> None:
        self.offset = offset

    def now(self) -> datetime:
        return SystemClock().now() + self.offset


def _secret(setup: dict[str, str]) -> bytes:
    raw = setup["secret"]
    return base64.b32decode(raw + "=" * (-len(raw) % 8))


def _code(secret: bytes, offset: timedelta = timedelta(0)) -> str:
    return totp.code_at(secret, totp.step_at(datetime.now(UTC) + offset))


def _login(client: TestClient, t: TenantFixture, email: str):  # type: ignore[no-untyped-def]
    return client.post(
        f"{API}/auth/login", json={"workspace_code": t.code, "email": email, "password": PASSWORD}
    )


def _enroll(client: TestClient, headers: dict[str, str]) -> tuple[bytes, list[str]]:
    setup = client.post(f"{API}/me/mfa/setup", headers=headers)
    assert setup.status_code == 200, setup.text
    secret = _secret(setup.json())
    confirmed = client.post(f"{API}/me/mfa/confirm", headers=headers, json={"code": _code(secret)})
    assert confirmed.status_code == 200, confirmed.text
    return secret, confirmed.json()["recovery_codes"]


def _verify(client: TestClient, t: TenantFixture, email: str, code: str):  # type: ignore[no-untyped-def]
    challenge = _login(client, t, email)
    assert challenge.status_code == 200 and challenge.json()["mfa_required"] is True, challenge.text
    return client.post(
        f"{API}/auth/mfa/verify", json={"mfa_token": challenge.json()["mfa_token"], "code": code}
    )


def test_soft_enrollment_limits_a_sensitive_role_to_its_account(
    client: TestClient, api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = api.tenant()
    hr = api.user(t, "HR")
    dispatcher = api.user(t, "DISPATCHER", "SITE", "S1")
    other_session = api.login(t.code, hr.email)
    # Comptes créés par l'administrateur avant l'obligation (lui-même sans second facteur).
    monkeypatch.setattr(get_settings(), "mfa_enforcement", "enroll")
    blocked = client.get(f"{API}/drivers", headers=hr.headers)
    assert (blocked.status_code, blocked.json()["code"]) == (403, "MFA_ENROLLMENT_REQUIRED")
    me = client.get(f"{API}/me", headers=hr.headers).json()
    assert me["mfa_enrollment_required"] is True and me["mfa_enabled"] is False
    status = client.get(f"{API}/me/mfa", headers=hr.headers).json()
    assert status == {"enabled": False, "required": True, "enabled_at": None, "recovery_codes_remaining": 0}
    # Un rôle non concerné (dispatcher) n'est pas bloqué.
    assert client.get(f"{API}/drivers", headers=dispatcher.headers).status_code == 200

    setup = client.post(f"{API}/me/mfa/setup", headers=hr.headers)
    assert setup.headers["Cache-Control"] == "no-store"
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/")
    wrong = client.post(f"{API}/me/mfa/confirm", headers=hr.headers, json={"code": "000000"})
    assert (wrong.status_code, wrong.json()["code"]) == (401, "MFA_CODE_INVALID")
    secret = _secret(setup.json())
    confirmed = client.post(f"{API}/me/mfa/confirm", headers=hr.headers, json={"code": _code(secret)})
    assert confirmed.status_code == 200
    assert len(confirmed.json()["recovery_codes"]) == 10
    # La session qui a prouvé le second facteur continue ; l'autre (mot de passe seul) est fermée.
    assert client.get(f"{API}/drivers", headers=hr.headers).status_code == 200
    assert client.get(f"{API}/me", headers=other_session).status_code == 401
    again = client.post(f"{API}/me/mfa/setup", headers=hr.headers)
    assert (again.status_code, again.json()["code"]) == (409, "MFA_ALREADY_ENABLED")


def test_login_requires_second_factor_and_refuses_replay(client: TestClient, api: Api) -> None:
    t = api.tenant()
    hr = api.user(t, "HR")
    secret, _ = _enroll(client, hr.headers)

    challenge = _login(client, t, hr.email)
    body = challenge.json()
    assert challenge.status_code == 200 and "access_token" not in body and body["expires_in"] == 300
    assert "mf_refresh" not in challenge.headers.get(
        "set-cookie", ""
    )  # aucune session sur le mot de passe seul
    # Le jeton de défi n'est pas un jeton d'accès.
    assert client.get(f"{API}/me", headers=bearer(body["mfa_token"])).status_code == 401

    # Le code de l'enrôlement (même pas de 30 s) ne peut pas être rejoué.
    replay = client.post(
        f"{API}/auth/mfa/verify", json={"mfa_token": body["mfa_token"], "code": _code(secret)}
    )
    assert (replay.status_code, replay.json()["code"]) == (401, "MFA_CODE_INVALID")
    # Pas suivant : dans la fenêtre de tolérance (dérive d'horloge du téléphone) et jamais utilisé.
    ok = client.post(
        f"{API}/auth/mfa/verify",
        json={"mfa_token": body["mfa_token"], "code": _code(secret, timedelta(seconds=30))},
    )
    assert ok.status_code == 200, ok.text
    assert "mf_refresh=" in ok.headers["set-cookie"]
    assert client.get(f"{API}/drivers", headers=bearer(ok.json()["access_token"])).status_code == 200
    refreshed = client.post(f"{API}/auth/refresh")
    assert refreshed.status_code == 200  # session marquée otp : le rafraîchissement reste possible

    events = client.get(
        f"{API}/audit-events", headers=t.admin.headers, params={"action": "auth.mfa_verify"}
    ).json()["items"]
    assert {(e["outcome"], e["reason"]) for e in events} >= {
        ("FAILURE", "MFA_CODE_INVALID"),
        ("SUCCESS", "TOTP"),
    }
    assert all("secret" not in str(e).lower() for e in events)


def test_recovery_code_is_single_use(client: TestClient, api: Api) -> None:
    t = api.tenant()
    hr = api.user(t, "HR")
    _, codes = _enroll(client, hr.headers)
    first = _verify(client, t, hr.email, codes[0].lower())
    assert first.status_code == 200, first.text
    reused = _verify(client, t, hr.email, codes[0])
    assert (reused.status_code, reused.json()["code"]) == (401, "MFA_CODE_INVALID")
    status = client.get(f"{API}/me/mfa", headers=bearer(first.json()["access_token"])).json()
    assert status["recovery_codes_remaining"] == 9


def test_second_factor_brute_force_is_rate_limited(client: TestClient, api: Api) -> None:
    t = api.tenant()
    hr = api.user(t, "HR")
    _enroll(client, hr.headers)
    token = _login(client, t, hr.email).json()["mfa_token"]
    statuses = [
        client.post(f"{API}/auth/mfa/verify", json={"mfa_token": token, "code": f"{n:06d}"}).status_code
        for n in range(get_settings().login_max_failures + 1)
    ]
    assert statuses[-1] == 429 and set(statuses[:-1]) == {401}


def test_expired_or_forged_challenge_is_refused(
    client: TestClient, api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = api.tenant()
    hr = api.user(t, "HR")
    secret, _ = _enroll(client, hr.headers)
    token = _login(client, t, hr.email).json()["mfa_token"]
    monkeypatch.setattr(client.app.state, "clock", OffsetClock(timedelta(minutes=6)))  # type: ignore[attr-defined]
    late = client.post(
        f"{API}/auth/mfa/verify", json={"mfa_token": token, "code": _code(secret, timedelta(minutes=6))}
    )
    assert (late.status_code, late.json()["code"]) == (401, "MFA_CODE_INVALID")
    forged = client.post(f"{API}/auth/mfa/verify", json={"mfa_token": token[:-4] + "AAAA", "code": "123456"})
    assert forged.status_code == 401


def test_admin_resets_a_lost_second_factor(client: TestClient, api: Api) -> None:
    t, other = api.tenant(), api.tenant()
    hr = api.user(t, "HR")
    _enroll(client, hr.headers)
    url = f"{API}/users/{hr.user_id}"
    version = client.get(url, headers=t.admin.headers).headers["ETag"]
    foreign = client.post(f"{url}/reset-mfa", headers={**other.admin.headers, "If-Match": version})
    assert foreign.status_code == 404  # utilisateur d'une autre société : indiscernable d'un inexistant
    reset = client.post(f"{url}/reset-mfa", headers={**t.admin.headers, "If-Match": version})
    assert reset.status_code == 200, reset.text
    assert client.get(f"{API}/me", headers=hr.headers).status_code == 401  # sessions fermées
    fresh = _login(client, t, hr.email)
    assert "access_token" in fresh.json()  # plus de défi : réenrôlement à la prochaine connexion
    me_url = f"{API}/users/{t.admin.user_id}"
    self_reset = client.post(
        f"{me_url}/reset-mfa",
        headers={**t.admin.headers, "If-Match": client.get(me_url, headers=t.admin.headers).headers["ETag"]},
    )
    assert self_reset.status_code == 422
    events = client.get(f"{API}/audit-events", headers=t.admin.headers, params={"action": "user.mfa_reset"})
    assert events.json()["total"] == 1


def test_disable_only_for_optional_roles(client: TestClient, api: Api) -> None:
    t = api.tenant()
    hr = api.user(t, "HR")
    secret, _ = _enroll(client, hr.headers)
    refused = client.post(
        f"{API}/me/mfa/disable", headers=hr.headers, json={"password": PASSWORD, "code": _code(secret)}
    )
    assert (refused.status_code, refused.json()["code"]) == (422, "MFA_REQUIRED_FOR_ROLE")
    dispatcher: Account = api.user(t, "DISPATCHER", "SITE", "S1")
    d_secret, _ = _enroll(client, dispatcher.headers)
    bad_password = client.post(
        f"{API}/me/mfa/disable", headers=dispatcher.headers, json={"password": "faux", "code": "000000"}
    )
    assert bad_password.status_code == 401
    # Le code de l'enrôlement est déjà consommé : il faut le pas suivant (anti-rejeu).
    replay = client.post(
        f"{API}/me/mfa/disable",
        headers=dispatcher.headers,
        json={"password": PASSWORD, "code": _code(d_secret)},
    )
    assert replay.status_code == 401
    del d_secret


def test_secret_is_never_stored_in_clear(client: TestClient, api: Api) -> None:
    t = api.tenant()
    hr = api.user(t, "HR")
    setup = client.post(f"{API}/me/mfa/setup", headers=hr.headers).json()
    client.post(f"{API}/me/mfa/confirm", headers=hr.headers, json={"code": _code(_secret(setup))})
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(t.tenant_id)})
        row = conn.execute(
            text(
                "SELECT mfa_secret_encrypted, mfa_recovery_hashes FROM user_account"
                " WHERE user_account_id = :u"
            ),
            {"u": str(hr.user_id)},
        ).one()
    engine.dispose()
    assert _secret(setup) not in bytes(row.mfa_secret_encrypted)
    assert setup["secret"].encode() not in bytes(row.mfa_secret_encrypted)
    assert len(row.mfa_recovery_hashes) == 10 and all(len(h) == 32 for h in row.mfa_recovery_hashes)


def test_ops_command_resets_platform_admin_second_factor(client: TestClient, api: Api) -> None:
    """Dernier recours : aucun compte au-dessus du PLATFORM_ADMIN ne peut lui retirer son second facteur."""
    from app.cli import main
    from tests.conftest import PLATFORM_EMAIL

    headers = api.platform()
    secret, _ = _enroll(client, headers)
    challenge = client.post(
        f"{API}/auth/platform/login", json={"email": PLATFORM_EMAIL, "password": PASSWORD}
    )
    assert challenge.json()["mfa_required"] is True
    assert main(["reset-platform-mfa", "--email", PLATFORM_EMAIL]) == 0
    assert client.get(f"{API}/me", headers=headers).status_code == 401  # sessions fermées
    fresh = client.post(f"{API}/auth/platform/login", json={"email": PLATFORM_EMAIL, "password": PASSWORD})
    assert "access_token" in fresh.json()
    api._platform = bearer(fresh.json()["access_token"])  # session partagée du harnais
    assert main(["reset-platform-mfa", "--email", PLATFORM_EMAIL]) == 3  # plus rien à retirer
    del secret
