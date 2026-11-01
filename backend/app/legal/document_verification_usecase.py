"""Complete server-side use case for document verification.

Caller must already have the legal.contract.review grant. It owns commit/rollback
and must not use identifiers or permissions supplied by an untrusted client.
"""

import uuid
from typing import Any

from app.legal.authorized_document_verification import verify_authorized_contract_document
from app.legal.document_verification_preflight import load_authorized_verification_context
from app.legal.malware_scan import MalwareScanner
from app.legal.private_storage import PrivateObjectStore


def verify_contract_pdf_usecase(
    db: Any,
    *,
    tenant_id: uuid.UUID,
    contract_id: uuid.UUID,
    document_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    review_permission_granted: bool,
    tenant_wide: bool,
    accessible_site_ids: frozenset[uuid.UUID],
    scanner: MalwareScanner,
    store: PrivateObjectStore,
) -> bool:
    """Use trusted row metadata to check reviewers before S3 access.

    The calling API must enforce RBAC before invoking this function and must
    rollback its transaction on any exception.
    """
    context = load_authorized_verification_context(
        db,
        tenant_id=tenant_id,
        contract_id=contract_id,
        document_id=document_id,
        actor_user_id=actor_user_id,
        review_permission_granted=review_permission_granted,
        tenant_wide=tenant_wide,
        accessible_site_ids=accessible_site_ids,
    )
    if context is None:
        return False
    return verify_authorized_contract_document(
        db,
        context=context,
        contract_id=contract_id,
        document_id=document_id,
        scanner=scanner,
        store=store,
    )
