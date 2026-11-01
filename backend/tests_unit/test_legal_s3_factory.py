"""The S3 factory must not connect unless explicitly enabled."""

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.legal.s3_factory import build_private_contract_store


def settings(**extra: object) -> Settings:
    data = {
        "MF_APP_PASSWORD": "test-password",
        "MF_JWT_SECRET": "a" * 40,
        "legal_object_storage_enabled": True,
        "legal_object_storage_endpoint": "https://storage.example.test",
        "legal_object_storage_bucket": "private-bucket",
        "legal_object_storage_access_key": "example-key",
        "legal_object_storage_secret_key": "example-secret",
    }
    data.update(extra)
    return Settings(**data)


def test_disabled_store_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="disabled"):
        build_private_contract_store(settings(legal_object_storage_enabled=False))


def test_factory_uses_private_credentials_without_network() -> None:
    fake_client = MagicMock()
    with patch("boto3.client", return_value=fake_client) as create_client:
        store = build_private_contract_store(settings())
    assert store.bucket == "private-bucket"
    assert store.client is fake_client
    create_client.assert_called_once_with(
        "s3",
        endpoint_url="https://storage.example.test",
        aws_access_key_id="example-key",
        aws_secret_access_key="example-secret",
        region_name="us-east-1",
    )
