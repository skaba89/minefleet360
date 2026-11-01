"""Authorized read-only reconciliation service.

The caller must provide the tenant ID from a verified authenticated context.
Never accept a tenant ID supplied by a request payload.
"""

import uuid
from typing import Any

from app.legal.reconciliation_adapters import reconcile_tenant_contract_objects
from app.legal.reconciliation_report import (
    DocumentReconciliationSummary,
    summarize_document_reconciliation,
)


def summarize_tenant_contract_storage(
    *,
    authenticated_tenant_id: uuid.UUID,
    s3_client: Any,
    bucket: str,
    db: Any,
) -> DocumentReconciliationSummary:
    """Return only aggregate counts, never private object keys."""
    if authenticated_tenant_id.int == 0:
        raise PermissionError("authenticated tenant required")
    result = reconcile_tenant_contract_objects(
        tenant_id=authenticated_tenant_id,
        s3_client=s3_client,
        bucket=bucket,
        db=db,
    )
    return summarize_document_reconciliation(result)
