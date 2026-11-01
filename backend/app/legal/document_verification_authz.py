"""Fail-closed authorization gate before contract document re-verification.

The HTTP boundary must independently enforce an authenticated review grant.
No database, antivirus or storage operation may happen before this policy passes.
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ContractDocumentVerificationContext:
    authenticated_tenant_id: uuid.UUID
    contract_tenant_id: uuid.UUID
    contract_site_id: uuid.UUID
    contract_status: str
    actor_user_id: uuid.UUID
    uploader_user_id: uuid.UUID
    review_permission_granted: bool
    tenant_wide: bool
    accessible_site_ids: frozenset[uuid.UUID]


def document_verification_allowed(context: ContractDocumentVerificationContext) -> bool:
    """Only a distinct authorized reviewer can verify a draft contract's PDF."""
    return (
        context.authenticated_tenant_id.int != 0
        and context.actor_user_id.int != 0
        and context.authenticated_tenant_id == context.contract_tenant_id
        and context.review_permission_granted
        and context.contract_status == "DRAFT"
        and context.actor_user_id != context.uploader_user_id
        and (context.tenant_wide or context.contract_site_id in context.accessible_site_ids)
    )
