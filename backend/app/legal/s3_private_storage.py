"""S3-compatible adapter for private contract PDF objects.

The application must provide a preconfigured client with private credentials.
Do not create a bucket or enable public read access here.
"""

from typing import Any


class S3PrivateObjectStore:
    def __init__(self, client: Any, bucket: str) -> None:
        if not bucket or "/" in bucket:
            raise ValueError("invalid bucket name")
        self.client = client
        self.bucket = bucket

    def put(self, *, key: str, content: bytes) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType="application/pdf",
            ServerSideEncryption="AES256",
        )

    def get(self, *, key: str) -> bytes:
        result = self.client.get_object(Bucket=self.bucket, Key=key)
        payload = result["Body"].read()
        if not isinstance(payload, bytes):
            raise ValueError("invalid object content")
        return payload
