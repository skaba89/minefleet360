"""Explicit S3/MinIO client factory; refuses disabled storage.

The boto3 client is imported only when storage is explicitly enabled.
"""

from typing import Any

from app.core.config import Settings
from app.legal.s3_private_storage import S3PrivateObjectStore


def build_private_contract_store(settings: Settings) -> S3PrivateObjectStore:
    """Create a private store using only validated server-side credentials."""
    if not settings.legal_object_storage_enabled:
        raise RuntimeError("private contract storage is disabled")
    if (
        not settings.legal_object_storage_access_key
        or not settings.legal_object_storage_secret_key
        or not settings.legal_object_storage_endpoint.startswith("https://")
        or not settings.legal_object_storage_bucket
    ):
        raise RuntimeError("private contract storage configuration is incomplete")
    import boto3

    client: Any = boto3.client(
        "s3",
        endpoint_url=settings.legal_object_storage_endpoint,
        aws_access_key_id=settings.legal_object_storage_access_key.get_secret_value(),
        aws_secret_access_key=settings.legal_object_storage_secret_key.get_secret_value(),
        region_name="us-east-1",
    )
    return S3PrivateObjectStore(client, settings.legal_object_storage_bucket)
