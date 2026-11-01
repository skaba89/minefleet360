"""Document upload authorization fails closed across tenants and sites."""

import uuid

import pytest

from app.legal.document_upload_policy import (
    DocumentUploadContext,
    contract_document_upload_allowed,
)


def context(**changes: object) -> DocumentUploadContext:
    tenant, site = TENANT, SITE
    fields = {
        "authenticated_tenant_id": tenant,
        "contract_tenant_id": tenant,
        "contract_site_id": site,
        "accessible_site_ids": frozenset({site}),
        "tenant_wide": False,
        "contract_status": "DRAFT",
    }
    fields.update(changes)
    return DocumentUploadContext(**fields)  # type: ignore[arg-type]


TENANT = uuid.uuid4()
SITE = uuid.uuid4()


def test_draft_same_tenant_and_site_allowed() -> None:
    assert contract_document_upload_allowed(context())
    assert contract_document_upload_allowed(context(accessible_site_ids=frozenset(), tenant_wide=True))


@pytest.mark.parametrize(
    "changes",
    [
        {"contract_tenant_id": uuid.uuid4()},
        {"authenticated_tenant_id": uuid.UUID(int=0)},
        {"contract_site_id": uuid.UUID(int=0)},
        {"accessible_site_ids": frozenset()},
        {"contract_status": "PENDING_REVIEW"},
        {"contract_status": "APPROVED"},
        {"contract_status": "REJECTED"},
    ],
)
def test_denies_cross_tenant_site_and_non_drafts(changes: dict[str, object]) -> None:
    assert not contract_document_upload_allowed(context(**changes))
