"""Resolve trusted contract/document ownership before document verification.

The caller must already hold the legal.contract.review grant. This module
does not expose an HTTP endpoint or perform storage side effects.
"""

import uuid
from typing import Any

from sqlalchemy import text

from app.legal.document_verification_authz import (
    ContractDocumentVerificationContext,
    document_verification_allowed,
)


def load_authorized_verification_context(
    db: Any,
    *,
    tenant_id: uuid.UUID,
    contract_id: uuid.UUID,
    document_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    review_permission_granted: bool,
    tenant_wide: bool,
    accessible_site_ids: frozenset[uuid.UUID],
) -> ContractDocumentVerificationContext | None:
    """Read ownership from the DB, reject foreign/self-review before S3 access."""
    if any(value.int == 0 for value in (tenant_id, contract_id, document_id, actor_user_id)):
        return None
    if not review_permission_granted:
        return None
    row = db.execute(
        text(
            "SELECT c.tenant_id, c.site_id, c.status, d.uploaded_by "
            "FROM legal_contract c JOIN legal_contract_document d "
            "ON d.tenant_id = c.tenant_id AND d.contract_id = c.contract_id "
            "WHERE c.tenant_id = :tenant AND c.contract_id = :contract "
            "AND d.document_id = :document AND d.status = 'PENDING' "
            "FOR UPDATE OF c, d"
        ),
        {"tenant": tenant_id, "contract": contract_id, "document": document_id},
    ).first()
    if row is None:
        return None
    context = ContractDocumentVerificationContext(
        authenticated_tenant_id=tenant_id,
        contract_tenant_id=row[0],
        contract_site_id=row[1],
        contract_status=row[2],
        actor_user_id=actor_user_id,
        uploader_user_id=row[3],
        review_permission_granted=review_permission_granted,
        tenant_wide=tenant_wide,
        accessible_site_ids=accessible_site_ids,
    )
    return context if document_verification_allowed(context) else None
