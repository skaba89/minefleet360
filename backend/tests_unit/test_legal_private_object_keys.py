"""Private contract object keys must not be predictable or user-controlled."""

import uuid

import pytest

from app.legal.private_object_keys import contract_document_key


def test_keys_are_tenant_and_contract_scoped_and_unique() -> None:
    tenant = uuid.uuid4()
    contract = uuid.uuid4()
    first = contract_document_key(tenant, contract)
    second = contract_document_key(tenant, contract)
    assert first != second
    assert first.startswith(f"legal/{tenant}/contracts/{contract}/")
    assert first.endswith(".pdf")
    assert "://" not in first
    assert ".." not in first


def test_keys_change_across_tenants_and_contracts() -> None:
    tenant = uuid.uuid4()
    contract = uuid.uuid4()
    first = contract_document_key(tenant, contract)
    assert first != contract_document_key(uuid.uuid4(), contract)
    assert first != contract_document_key(tenant, uuid.uuid4())


@pytest.mark.parametrize(
    "tenant,contract",
    [(uuid.UUID(int=0), uuid.uuid4()), (uuid.uuid4(), uuid.UUID(int=0))],
)
def test_nil_ids_rejected(tenant: uuid.UUID, contract: uuid.UUID) -> None:
    with pytest.raises(ValueError):
        contract_document_key(tenant, contract)
