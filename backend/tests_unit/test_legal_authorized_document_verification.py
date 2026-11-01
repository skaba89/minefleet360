"""Authorization must precede storage, scanning, SQL update or audit."""

import uuid
from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from app.legal import authorized_document_verification as bridge
from app.legal.document_verification_authz import ContractDocumentVerificationContext


def context() -> ContractDocumentVerificationContext:
    tenant_id = uuid.uuid4()
    return ContractDocumentVerificationContext(
        authenticated_tenant_id=tenant_id,
        contract_tenant_id=tenant_id,
        contract_site_id=uuid.uuid4(),
        contract_status="DRAFT",
        actor_user_id=uuid.uuid4(),
        uploader_user_id=uuid.uuid4(),
        review_permission_granted=True,
        tenant_wide=True,
        accessible_site_ids=frozenset(),
    )


def test_authorized_reviewer_runs_transactional_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    service = MagicMock(return_value=True)
    monkeypatch.setattr(bridge, "verify_pending_contract_document", service)
    ctx = context()
    db, scanner, store = MagicMock(), MagicMock(), MagicMock()
    contract_id, document_id = uuid.uuid4(), uuid.uuid4()
    assert bridge.verify_authorized_contract_document(
        db,
        context=ctx,
        contract_id=contract_id,
        document_id=document_id,
        scanner=scanner,
        store=store,
    )
    assert service.call_args.kwargs["tenant_id"] == ctx.authenticated_tenant_id
    assert service.call_args.kwargs["actor_user_id"] == ctx.actor_user_id
    assert service.call_args.kwargs["contract_id"] == contract_id
    db.commit.assert_not_called()


@pytest.mark.parametrize("failure", ["other_tenant", "self_review", "no_grant", "other_site", "not_draft"])
def test_denied_reviewer_has_zero_side_effects(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    service = MagicMock()
    monkeypatch.setattr(bridge, "verify_pending_contract_document", service)
    ctx = context()
    if failure == "other_tenant":
        ctx = replace(ctx, contract_tenant_id=uuid.uuid4())
    elif failure == "self_review":
        ctx = replace(ctx, uploader_user_id=ctx.actor_user_id)
    elif failure == "no_grant":
        ctx = replace(ctx, review_permission_granted=False)
    elif failure == "other_site":
        ctx = replace(ctx, tenant_wide=False)
    else:
        ctx = replace(ctx, contract_status="PENDING_REVIEW")
    db, scanner, store = MagicMock(), MagicMock(), MagicMock()
    with pytest.raises(PermissionError):
        bridge.verify_authorized_contract_document(
            db, context=ctx, contract_id=uuid.uuid4(), document_id=uuid.uuid4(),
            scanner=scanner, store=store,
        )
    service.assert_not_called()
    db.execute.assert_not_called()
    store.get.assert_not_called()
    scanner.scan.assert_not_called()
