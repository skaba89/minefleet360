"""Document status transition requires proof and strict tenant ownership."""

import uuid
from unittest.mock import MagicMock

import pytest

from app.legal.document_verification_transition import mark_reverified_contract_document


def test_verified_transition_is_scoped_and_requires_pending() -> None:
    db = MagicMock()
    db.execute.return_value.first.return_value = (uuid.uuid4(),)
    tenant_id, contract_id, document_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    assert mark_reverified_contract_document(
        db,
        tenant_id=tenant_id,
        contract_id=contract_id,
        document_id=document_id,
        trusted_reverification_passed=True,
    )
    sql = str(db.execute.call_args.args[0])
    assert "status = 'PENDING'" in sql
    assert "tenant_id = :tenant" in sql
    assert "contract_id = :contract" in sql
    assert "document_id = :document" in sql
    assert db.execute.call_args.args[1] == {
        "tenant": tenant_id,
        "contract": contract_id,
        "document": document_id,
    }
    db.commit.assert_not_called()


def test_unverified_document_cannot_transition() -> None:
    db = MagicMock()
    with pytest.raises(PermissionError, match="reverification"):
        mark_reverified_contract_document(
            db,
            tenant_id=uuid.uuid4(),
            contract_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            trusted_reverification_passed=False,
        )
    db.execute.assert_not_called()


def test_invalid_owner_is_rejected_before_sql() -> None:
    db = MagicMock()
    with pytest.raises(ValueError, match="ownership"):
        mark_reverified_contract_document(
            db,
            tenant_id=uuid.UUID(int=0),
            contract_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            trusted_reverification_passed=True,
        )
    db.execute.assert_not_called()


def test_non_pending_or_missing_document_does_not_transition() -> None:
    db = MagicMock()
    db.execute.return_value.first.return_value = None
    assert not mark_reverified_contract_document(
        db,
        tenant_id=uuid.uuid4(),
        contract_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        trusted_reverification_passed=True,
    )
    db.commit.assert_not_called()
