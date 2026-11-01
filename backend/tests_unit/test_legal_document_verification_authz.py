"""Permission and four-eyes policy for contract PDF verification."""

import uuid
from dataclasses import replace

import pytest

from app.legal.document_verification_authz import (
    ContractDocumentVerificationContext,
    document_verification_allowed,
)


def allowed_context() -> ContractDocumentVerificationContext:
    site_id = uuid.uuid4()
    return ContractDocumentVerificationContext(
        authenticated_tenant_id=uuid.uuid4(),
        contract_tenant_id=uuid.UUID(int=0),
        contract_site_id=site_id,
        contract_status="DRAFT",
        actor_user_id=uuid.uuid4(),
        uploader_user_id=uuid.uuid4(),
        review_permission_granted=True,
        tenant_wide=False,
        accessible_site_ids=frozenset({site_id}),
    )


def test_authorized_independent_site_reviewer() -> None:
    ctx = allowed_context()
    ctx = replace(ctx, contract_tenant_id=ctx.authenticated_tenant_id)
    assert document_verification_allowed(ctx)


def test_authorized_tenant_reviewer() -> None:
    ctx = allowed_context()
    ctx = replace(
        ctx,
        contract_tenant_id=ctx.authenticated_tenant_id,
        tenant_wide=True,
        accessible_site_ids=frozenset(),
    )
    assert document_verification_allowed(ctx)


@pytest.mark.parametrize(
    "change",
    ["cross_tenant", "missing_permission", "foreign_site", "self_review", "non_draft", "zero_actor"],
)
def test_rejects_unauthorized_verification(change: str) -> None:
    ctx = allowed_context()
    ctx = replace(ctx, contract_tenant_id=ctx.authenticated_tenant_id)
    if change == "cross_tenant":
        ctx = replace(ctx, contract_tenant_id=uuid.uuid4())
    elif change == "missing_permission":
        ctx = replace(ctx, review_permission_granted=False)
    elif change == "foreign_site":
        ctx = replace(ctx, accessible_site_ids=frozenset())
    elif change == "self_review":
        ctx = replace(ctx, uploader_user_id=ctx.actor_user_id)
    elif change == "non_draft":
        ctx = replace(ctx, contract_status="PENDING_REVIEW")
    else:
        ctx = replace(ctx, actor_user_id=uuid.UUID(int=0))
    assert not document_verification_allowed(ctx)
