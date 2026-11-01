"""Fail-closed authorization policy for future contract-document uploads.

Only the API may resolve tenant, site and actor from authenticated context.
Never take these identifiers from a file-upload request body.
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentUploadContext:
    authenticated_tenant_id: uuid.UUID
    contract_tenant_id: uuid.UUID
    contract_site_id: uuid.UUID
    accessible_site_ids: frozenset[uuid.UUID]
    tenant_wide: bool
    contract_status: str


def contract_document_upload_allowed(context: DocumentUploadContext) -> bool:
    """Uploading must not cross tenant/site boundaries or alter a submitted contract."""
    return (
        context.authenticated_tenant_id.int != 0
        and context.authenticated_tenant_id == context.contract_tenant_id
        and context.contract_site_id.int != 0
        and (context.tenant_wide or context.contract_site_id in context.accessible_site_ids)
        and context.contract_status == "DRAFT"
    )
