"""Storage configuration is opt-in and rejects insecure endpoints."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def configured(**overrides: object) -> Settings:
    values = {
        "MF_APP_PASSWORD": "test-db-password",
        "MF_JWT_SECRET": "a" * 40,
        "MF_LEGAL_OBJECT_STORAGE_ENABLED": True,
        "MF_LEGAL_OBJECT_STORAGE_ENDPOINT": "https://storage.example.test",
        "MF_LEGAL_OBJECT_STORAGE_BUCKET": "minefleet-private",
        "MF_LEGAL_OBJECT_STORAGE_ACCESS_KEY": "test-access",
        "MF_LEGAL_OBJECT_STORAGE_SECRET_KEY": "test-secret",
    }
    values.update(overrides)
    return Settings(**values)


def test_secure_object_storage_config() -> None:
    assert configured().legal_object_storage_enabled


@pytest.mark.parametrize(
    "invalid",
    [
        {"MF_LEGAL_OBJECT_STORAGE_ENDPOINT": "http://storage.example.test"},
        {"MF_LEGAL_OBJECT_STORAGE_BUCKET": ""},
        {"MF_LEGAL_OBJECT_STORAGE_BUCKET": "folder/bucket"},
        {"MF_LEGAL_OBJECT_STORAGE_SECRET_KEY": None},
    ],
)
def test_insecure_storage_config_rejected(invalid: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        configured(**invalid)
