"""TOTP (RFC 6238), codes de récupération et chiffrement des secrets (C-03)."""

from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from app.core import totp
from app.core.config import Settings
from app.core.secretbox import open_sealed, seal

RFC_SECRET = b"12345678901234567890"  # RFC 6238 annexe B (SHA1)


def test_rfc6238_reference_vectors_truncated_to_six_digits() -> None:
    # Valeurs à 8 chiffres de la RFC : 94287082, 07081804, 14050471, 89005924 → 6 derniers chiffres.
    for seconds, expected in (
        (59, "287082"),
        (1111111109, "081804"),
        (1111111111, "050471"),
        (1234567890, "005924"),
    ):
        assert totp.code_at(RFC_SECRET, seconds // 30) == expected


def test_window_tolerates_one_step_of_clock_drift_and_refuses_replay() -> None:
    now = datetime(2026, 10, 27, 8, 0, 15, tzinfo=UTC)
    step = totp.step_at(now)
    previous = totp.code_at(RFC_SECRET, step - 1)
    assert totp.verify(RFC_SECRET, previous, now, last_step=None) == step - 1
    assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, step + 1), now, last_step=None) == step + 1
    assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, step - 2), now, last_step=None) is None
    # Anti-rejeu : un pas déjà accepté (ou antérieur) ne l'est plus.
    assert totp.verify(RFC_SECRET, previous, now, last_step=step - 1) is None
    assert totp.verify(RFC_SECRET, "12345", now, last_step=None) is None
    assert totp.verify(RFC_SECRET, "abcdef", now, last_step=None) is None


def test_provisioning_uri_is_standard() -> None:
    uri = totp.provisioning_uri(RFC_SECRET, account="admin@example.com", issuer="MINEFLEET 360")
    assert uri.startswith("otpauth://totp/MINEFLEET%20360%3Aadmin%40example.com?secret=GEZDGNBVGY3TQOJQ")
    assert "issuer=MINEFLEET%20360" in uri and "digits=6" in uri and "period=30" in uri


def test_recovery_codes_are_unique_unambiguous_and_hashed() -> None:
    codes = totp.new_recovery_codes()
    assert len(set(codes)) == 10
    for code in codes:
        assert len(code) == 11 and code[5] == "-"
        assert not set(code.replace("-", "")) & set("01OI")
        assert totp.looks_like_recovery_code(code.lower())
        assert totp.hash_recovery_code(code) == totp.hash_recovery_code(code.lower().replace("-", " "))
    assert not totp.looks_like_recovery_code("123456")


def _settings(**extra: object) -> Settings:
    return Settings(app_password=SecretStr("x"), jwt_secret=SecretStr("j" * 40), env="test", **extra)  # type: ignore[arg-type]


def test_secret_sealing_is_bound_to_its_context_and_key() -> None:
    settings = _settings()
    sealed = seal(RFC_SECRET, context="mfa:t1:u1", settings=settings)
    assert RFC_SECRET not in sealed
    assert open_sealed(sealed, context="mfa:t1:u1", settings=settings) == RFC_SECRET
    assert open_sealed(sealed, context="mfa:t1:u2", settings=settings) is None  # recopié sur un autre compte
    tampered = sealed[:-1] + bytes([sealed[-1] ^ 1])
    assert open_sealed(tampered, context="mfa:t1:u1", settings=settings) is None
    other_key = _settings(MF_MFA_ENCRYPTION_KEY=SecretStr("A" * 43))
    assert open_sealed(sealed, context="mfa:t1:u1", settings=other_key) is None


def test_key_is_mandatory_on_servers() -> None:
    with pytest.raises(ValueError, match="MF_MFA_ENCRYPTION_KEY"):
        Settings(app_password=SecretStr("x"), jwt_secret=SecretStr("j" * 40), env="staging")  # type: ignore[arg-type]
