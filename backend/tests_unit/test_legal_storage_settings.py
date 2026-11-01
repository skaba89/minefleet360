"""Storage configuration is opt-in and rejects insecure endpoints."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def configured(**overrides: object) -> Settings:
    values = {
        "MF_APP_PASSWORD": "test-db-password",
        "MF_JWT_SECRET": "a" * 40,
        "legal_object_storage_enabled": True,
        "legal_object_storage_endpoint": "https://storage.example.test",
        "legal_object_storage_bucket": "minefleet-private",
        "legal_object_storage_access_key": "test-access",
        "legal_object_storage_secret_key": "test-secret",
    }
    values.update(overrides)
    return Settings(**values)


def test_secure_object_storage_config() -> None:
    assert configured().legal_object_storage_enabled


@pytest.mark.parametrize(
    "invalid",
    [
        {"legal_object_storage_endpoint": "http://storage.example.test"},
        {"legal_object_storage_bucket": ""},
        {"legal_object_storage_bucket": "folder/bucket"},
        {"legal_object_storage_secret_key": None},
    ],
)
def test_insecure_storage_config_rejected(invalid: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        configured(**invalid)
