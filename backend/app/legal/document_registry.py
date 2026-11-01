"""Persist scanned document metadata as PENDING, never as VERIFIED.

Call only after authenticated tenant/site checks and secure PDF ingestion.
The database transaction and audit belong to the API orchestration layer.
"""

import uuid
from typing import Any

from sqlalchemy import text

from app.legal.document_ingestion import IngestedPDF


def record_pending_contract_document(
    db: Any,
    *,
    tenant_id: uuid.UUID,
    contract_id: uuid.UUID,
    actor_id: uuid.UUID,
    original_filename: str,
    document: IngestedPDF,
) -> uuid.UUID:
    """Record a scanned and stored PDF, without granting review eligibility."""
    name = original_filename.strip()
    if not name or len(name) > 255 or "/" in name or "\\" in name:
        raise ValueError("invalid document filename")
    if tenant_id.int == 0 or contract_id.int == 0 or actor_id.int == 0:
        raise ValueError("missing document ownership")
    row = db.execute(
        text(
            "INSERT INTO legal_contract_document "
            "(tenant_id, contract_id, uploaded_by, original_filename, "
            "content_type, object_key, sha256, byte_size, status) "
            "VALUES (:tenant, :contract, :actor, :name, "
            "'application/pdf', :key, :sha, :size, 'PENDING') "
            "RETURNING document_id"
        ),
        {
            "tenant": tenant_id,
            "contract": contract_id,
            "actor": actor_id,
            "name": name,
            "key": document.object_key,
            "sha": document.sha256,
            "size": document.byte_size,
        },
    ).scalar_one()
    return uuid.UUID(str(row))
