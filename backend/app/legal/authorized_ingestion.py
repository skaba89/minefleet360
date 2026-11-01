"""Authorization gate for contract PDF ingestion before any external side effect.

The HTTP layer must separately enforce its RBAC permission and load the
contract from the authenticated tenant before constructing the context.
"""

import uuid

from app.legal.document_ingestion import IngestedPDF, ingest_contract_pdf
from app.legal.document_upload_policy import (
    DocumentUploadContext,
    contract_document_upload_allowed,
)
from app.legal.malware_scan import MalwareScanner
from app.legal.private_storage import PrivateObjectStore


def ingest_authorized_contract_pdf(
    *,
    context: DocumentUploadContext,
    contract_id: uuid.UUID,
    payload: bytes,
    scanner: MalwareScanner | None,
    store: PrivateObjectStore,
) -> IngestedPDF:
    """Reject unauthorized uploads before scanning or storing any bytes."""
    if contract_id.int == 0 or not contract_document_upload_allowed(context):
        raise PermissionError("contract document upload denied")
    return ingest_contract_pdf(
        tenant_id=context.authenticated_tenant_id,
        contract_id=contract_id,
        payload=payload,
        scanner=scanner,
        store=store,
    )
