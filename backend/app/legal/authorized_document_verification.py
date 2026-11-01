"""Authorized bridge for document verification. No external effects before policy checks."""

import uuid
from typing import Any

from app.legal.document_verification_authz import (
    ContractDocumentVerificationContext,
    document_verification_allowed,
)
from app.legal.document_verification_workflow import verify_pending_contract_document
from app.legal.malware_scan import MalwareScanner
from app.legal.private_storage import PrivateObjectStore


def verify_authorized_contract_document(
    db: Any,
    *,
    context: ContractDocumentVerificationContext,
    contract_id: uuid.UUID,
    document_id: uuid.UUID,
    scanner: MalwareScanner,
    store: PrivateObjectStore,
) -> bool:
    """Reject forbidden reviewers before any database or object-store operations.

    Caller must obtain trusted contract and uploader metadata and commit/rollback.
    """
    if contract_id.int == 0 or document_id.int == 0 or not document_verification_allowed(context):
        raise PermissionError("contract document verification denied")
    return verify_pending_contract_document(
        db,
        tenant_id=context.authenticated_tenant_id,
        contract_id=contract_id,
        document_id=document_id,
        actor_user_id=context.actor_user_id,
        scanner=scanner,
        store=store,
    )
