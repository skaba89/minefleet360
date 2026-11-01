"""Guarded database transition for a reverified contract PDF.

This function must only be called by a privileged orchestration layer after
reverify_stored_contract_pdf succeeds. It never commits its own transaction.
"""

import uuid
from typing import Any

from sqlalchemy import text


def mark_reverified_contract_document(
    db: Any,
    *,
    tenant_id: uuid.UUID,
    contract_id: uuid.UUID,
    document_id: uuid.UUID,
    trusted_reverification_passed: bool,
) -> bool:
    """Atomically mark one PENDING document VERIFIED, never a foreign document."""
    if not trusted_reverification_passed:
        raise PermissionError("trusted document reverification required")
    if any(value.int == 0 for value in (tenant_id, contract_id, document_id)):
        raise ValueError("missing document ownership")
    row = db.execute(
        text(
            "UPDATE legal_contract_document "
            "SET status = 'VERIFIED', verified_at = now(), "
            "stored_object_verified = true, malware_scan_passed = true "
            "WHERE tenant_id = :tenant AND contract_id = :contract AND document_id = :document "
            "AND status = 'PENDING' "
            "RETURNING document_id"
        ),
        {"tenant": tenant_id, "contract": contract_id, "document": document_id},
    ).first()
    return row is not None
