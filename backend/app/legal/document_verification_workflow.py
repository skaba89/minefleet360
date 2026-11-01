"""Transactional orchestration for privately stored contract PDF verification.

The HTTP boundary must enforce RBAC, tenant and site permissions before calling.
No public route or automatic approval is introduced here.
"""

import uuid
from typing import Any

from sqlalchemy import text

from app.audit.contracts import record
from app.legal.document_reverification import reverify_stored_contract_pdf
from app.legal.document_verification_transition import mark_reverified_contract_document
from app.legal.malware_scan import MalwareScanner
from app.legal.private_storage import PrivateObjectStore


def verify_pending_contract_document(
    db: Any,
    *,
    tenant_id: uuid.UUID,
    contract_id: uuid.UUID,
    document_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    scanner: MalwareScanner,
    store: PrivateObjectStore,
) -> bool:
    """Lock pending metadata; re-read/scan stored bytes; update and audit atomically.

    Caller owns commit/rollback. False means the document is absent or not PENDING.
    """
    if any(value.int == 0 for value in (tenant_id, contract_id, document_id, actor_user_id)):
        raise ValueError("missing document ownership")
    row = db.execute(
        text(
            "SELECT object_key, sha256, byte_size FROM legal_contract_document "
            "WHERE tenant_id = :tenant AND contract_id = :contract "
            "AND document_id = :document AND status = 'PENDING' FOR UPDATE"
        ),
        {"tenant": tenant_id, "contract": contract_id, "document": document_id},
    ).first()
    if row is None:
        return False
    reverified = reverify_stored_contract_pdf(
        tenant_id=tenant_id,
        contract_id=contract_id,
        object_key=row[0],
        expected_sha256=row[1],
        expected_size=row[2],
        scanner=scanner,
        store=store,
    )
    if not mark_reverified_contract_document(
        db,
        tenant_id=tenant_id,
        contract_id=contract_id,
        document_id=document_id,
        trusted_reverification_passed=reverified,
    ):
        raise RuntimeError("document state changed during verification")
    record(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="legal.contract.document.verify",
        entity_type="legal_contract_document",
        entity_id=document_id,
        before={"status": "PENDING"},
        after={"status": "VERIFIED"},
        changed_fields=["status", "verified_at", "stored_object_verified", "malware_scan_passed"],
    )
    return True
