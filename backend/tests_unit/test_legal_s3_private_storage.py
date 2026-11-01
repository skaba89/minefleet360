"""Contract tests for the S3-compatible private document adapter."""

from io import BytesIO
from typing import Any

import pytest

from app.legal.s3_private_storage import S3PrivateObjectStore


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.last_put: dict[str, Any] = {}

    def put_object(self, **kwargs: Any) -> None:
        self.last_put = kwargs
        self.objects[kwargs["Key"]] = kwargs["Body"]

    def get_object(self, **kwargs: Any) -> dict[str, BytesIO]:
        return {"Body": BytesIO(self.objects[kwargs["Key"]])}


def test_private_s3_put_and_get() -> None:
    client = FakeS3()
    store = S3PrivateObjectStore(client, "minefleet-private")
    store.put(key="legal/tenant/contracts/contract/doc.pdf", content=b"%PDF-1.7")
    assert store.get(key="legal/tenant/contracts/contract/doc.pdf") == b"%PDF-1.7"
    assert client.last_put["ServerSideEncryption"] == "AES256"
    assert client.last_put["ContentType"] == "application/pdf"
    assert "ACL" not in client.last_put


@pytest.mark.parametrize("bucket", ["", "folder/name"])
def test_invalid_bucket_rejected(bucket: str) -> None:
    with pytest.raises(ValueError):
        S3PrivateObjectStore(FakeS3(), bucket)
