"""Rotation de MF_MFA_ENCRYPTION_KEY sans perte d'accès (docs/ops/ROTATION_SECRETS.md)."""

import base64
import os
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text

from app.cli import main
from app.core.config import get_settings
from app.core.secretbox import open_sealed
from tests.conftest import API, Api
from tests.test_mfa import _code, _enroll, _verify


def _key() -> SecretStr:
    """Clé fictive tirée à chaque exécution : aucune valeur ressemblant à un secret dans le dépôt."""
    return SecretStr(base64.urlsafe_b64encode(os.urandom(32)).decode())


def _stored(tenant_id: str, user_id: str) -> bytes:
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})
            value = conn.execute(
                text("SELECT mfa_secret_encrypted FROM user_account WHERE user_account_id = :u"),
                {"u": user_id},
            ).scalar_one()
    finally:
        engine.dispose()
    return bytes(value)


def test_rotation_keeps_access_and_reseals_secrets(
    client: TestClient, api: Api, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = get_settings()
    old, new = _key(), _key()
    monkeypatch.setattr(settings, "mfa_encryption_key", old)
    t = api.tenant()
    hr = api.user(t, "HR")
    secret, codes = _enroll(client, hr.headers)
    before = _stored(str(t.tenant_id), str(hr.user_id))

    # Nouvelle clé en service, ancienne en secours : second facteur et codes de secours restent valables.
    monkeypatch.setattr(settings, "mfa_encryption_key", new)
    monkeypatch.setattr(settings, "mfa_encryption_key_previous", old)
    totp_login = _verify(client, t, hr.email, _code(secret, timedelta(seconds=30)))
    assert totp_login.status_code == 200, totp_login.text
    recovery_login = _verify(client, t, hr.email, codes[0])
    assert recovery_login.status_code == 200, recovery_login.text

    # Simulation : rien n'est modifié.
    assert main(["reseal-mfa-secrets"]) in (0, 3)  # 3 si d'autres comptes du harnais ont une autre clé
    assert _stored(str(t.tenant_id), str(hr.user_id)) == before
    assert "simulation" in capsys.readouterr().out
    # Application : le secret est rechiffré sous la nouvelle clé, sans jamais être affiché.
    assert main(["reseal-mfa-secrets", "--apply"]) in (0, 3)
    output = capsys.readouterr().out
    assert base64.b32encode(secret).decode() not in output
    after = _stored(str(t.tenant_id), str(hr.user_id))
    assert after != before
    audit = client.get(
        f"{API}/audit-events", headers=t.admin.headers, params={"action": "security.mfa_key_rotated"}
    ).json()["items"]
    assert len(audit) == 1 and audit[0]["after_data"] == {"resealed": 1}

    # Ancienne clé retirée : le secret rechiffré se lit avec la seule nouvelle clé…
    monkeypatch.setattr(settings, "mfa_encryption_key_previous", None)
    context = f"mfa:{t.tenant_id}:{hr.user_id}"
    assert open_sealed(after, context=context, settings=settings) == secret
    assert open_sealed(before, context=context, settings=settings) is None
    # …mais les codes de secours émis sous l'ancienne clé ne valent plus (non rechiffrables, documenté).
    stale = _verify(client, t, hr.email, codes[1])
    assert (stale.status_code, stale.json()["code"]) == (401, "MFA_CODE_INVALID")


def test_reseal_command_requires_both_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "mfa_encryption_key", _key())
    monkeypatch.setattr(settings, "mfa_encryption_key_previous", None)
    assert main(["reseal-mfa-secrets"]) == 2


def test_previous_key_identical_to_current_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    key = _key()
    monkeypatch.setattr(settings, "mfa_encryption_key", key)
    monkeypatch.setattr(settings, "mfa_encryption_key_previous", key)
    with pytest.raises(RuntimeError, match="identique"):
        open_sealed(b"\x01" + b"\x00" * 40, context="mfa:x:y", settings=settings)
