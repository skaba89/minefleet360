"""Read-only, tenant-bounded adapters for legal document reconciliation.

Callers must acquire the tenant context through the authenticated service layer.
"""

import uuid
from typing import Any

from sqlalchemy import text

from app.legal.document_reconciliation import DocumentReconciliation, reconcile_document_keys


def reconcile_tenant_contract_objects(
    *,
    tenant_id: uuid.UUID,
    s3_client: Any,
    bucket: str,
    db: Any,
) -> DocumentReconciliation:
    """List all tenant objects with pagination and compare to scoped SQL keys."""
    if tenant_id.int == 0 or not bucket or "/" in bucket:
        raise ValueError("invalid reconciliation scope")
    prefix = f"legal/{tenant_id}/"
    stored: list[str] = []
    continuation: str | None = None
    while True:
        options: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
        if continuation is not None:
            options["ContinuationToken"] = continuation
        page = s3_client.list_objects_v2(**options)
        for entry in page.get("Contents", []):
            key = entry["Key"]
            if not isinstance(key, str) or not key.startswith(prefix):
                raise ValueError("S3 returned an out-of-scope key")
            stored.append(key)
        if not page.get("IsTruncated", False):
            break
        token = page.get("NextContinuationToken")
        if not isinstance(token, str) or not token or token == continuation:
            raise ValueError("invalid S3 continuation token")
        continuation = token
    registered = db.execute(
        text("SELECT object_key FROM legal_contract_document WHERE tenant_id = :tenant"),
        {"tenant": tenant_id},
    ).scalars().all()
    return reconcile_document_keys(
        tenant_prefix=prefix,
        stored_keys=stored,
        registered_keys=registered,
    )
