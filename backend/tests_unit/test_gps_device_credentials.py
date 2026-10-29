"""Vérification cryptographique des secrets de traceurs GPS."""

import pytest

from app.fleet.gps_device_credentials import (
    fingerprint_device_secret,
    new_device_secret,
    verify_device_secret,
)

def test_new_secret_is_unique_and_verifiable() -> None:
    secret = new_device_secret()
    other = new_device_secret()
    assert len(secret) >= 32
    assert secret != other
    fingerprint = fingerprint_device_secret(secret)
    assert secret not in fingerprint
    assert verify_device_secret(fingerprint, secret)
    assert not verify_device_secret(fingerprint, other)


@pytest.mark.parametrize("secret", ["", "short", " " * 33, " x" * 17])
def test_rejects_weak_or_noncanonical_secrets(secret: str) -> None:
    with pytest.raises(ValueError):
        fingerprint_device_secret(secret)


def test_missing_or_malformed_fingerprint_is_rejected() -> None:
    secret = new_device_secret()
    assert not verify_device_secret(None, secret)
    assert not verify_device_secret("abc", secret)
    assert not verify_device_secret("Z" * 64, secret)
    assert not verify_device_secret(fingerprint_device_secret(secret), "bad")
