"""Fail-closed re-verification of a previously stored contract PDF.

This routine never updates SQL status or grants VERIFIED automatically.
"""

import re
import uuid

from app.legal.document_validation import inspect_contract_pdf
from app.legal.malware_scan import MalwareScanner, require_clean_pdf
from app.legal.private_storage import PrivateObjectStore


def reverify_stored_contract_pdf(
    *,
    tenant_id: uuid.UUID,
    contract_id: uuid.UUID,
    object_key: str,
    expected_sha256: str,
    expected_size: int,
    scanner: MalwareScanner | None,
    store: PrivateObjectStore,
) -> bool:
    """Verify ownership, stored bytes, original digest and fresh malware scan."""
    if tenant_id.int == 0 or contract_id.int == 0:
        raise ValueError("missing document ownership")
    prefix = f"legal/{tenant_id}/contracts/{contract_id}/"
    if not object_key.startswith(prefix) or not object_key.endswith(".pdf"):
        raise ValueError("document key does not match contract ownership")
    if ".." in object_key or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("invalid document metadata")
    if not 1 <= expected_size <= 25 * 1024 * 1024:
        raise ValueError("invalid document size")
    if scanner is None:
        raise ValueError("malware scanner unavailable")
    payload = store.get(key=object_key)
    digest, size = inspect_contract_pdf(payload)
    if digest != expected_sha256 or size != expected_size:
        raise ValueError("stored document integrity mismatch")
    require_clean_pdf(scanner, payload)
    return True
