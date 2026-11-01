"""Secure contract document ingestion service, independent of HTTP and database.

This gate never marks records VERIFIED. The API must enforce tenant/site
authorization and commit verified metadata only after trusted checks.
"""

from dataclasses import dataclass
import uuid

from app.legal.document_validation import inspect_contract_pdf
from app.legal.malware_scan import MalwareScanner, require_clean_pdf
from app.legal.private_object_keys import contract_document_key
from app.legal.private_storage import PrivateObjectStore, persist_contract_pdf


@dataclass(frozen=True)
class IngestedPDF:
    object_key: str
    sha256: str
    byte_size: int


def ingest_contract_pdf(
    *,
    tenant_id: uuid.UUID,
    contract_id: uuid.UUID,
    payload: bytes,
    scanner: MalwareScanner | None,
    store: PrivateObjectStore,
) -> IngestedPDF:
    """Validate, scan, write and read back. Fail closed on any exception."""
    digest, size = inspect_contract_pdf(payload)
    require_clean_pdf(scanner, payload)
    key = contract_document_key(tenant_id, contract_id)
    saved = persist_contract_pdf(store, key=key, payload=payload)
    confirmed_digest, confirmed_size = inspect_contract_pdf(saved.content)
    if confirmed_digest != digest or confirmed_size != size:
        raise ValueError("stored document integrity mismatch")
    return IngestedPDF(object_key=key, sha256=digest, byte_size=size)
