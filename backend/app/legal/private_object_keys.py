"""Opaque tenant-scoped object keys for future private document storage.

This module generates identifiers only. It does not upload or verify objects.
"""

import uuid


def contract_document_key(tenant_id: uuid.UUID, contract_id: uuid.UUID) -> str:
    """Generate a collision-resistant key without user-supplied filenames."""
    if tenant_id.int == 0 or contract_id.int == 0:
        raise ValueError("tenant and contract identifiers are required")
    return f"legal/{tenant_id}/contracts/{contract_id}/{uuid.uuid4().hex}.pdf"
