"""Pending registry persistence must not silently mark an upload verified."""

import uuid
from unittest.mock import MagicMock

import pytest

from app.legal.document_ingestion import IngestedPDF
from app.legal.document_registry import record_pending_contract_document


def test_registry_insert_is_pending_only() -> None:
    db = MagicMock()
    expected = uuid.uuid4()
    db.execute.return_value.scalar_one.return_value = expected
    tenant_id, contract_id = uuid.uuid4(), uuid.uuid4()
    result = record_pending_contract_document(
        db,
        tenant_id=tenant_id,
        contract_id=contract_id,
        actor_id=uuid.uuid4(),
        original_filename="agreement.pdf",
        document=IngestedPDF(
            object_key=f"legal/{tenant_id}/contracts/{contract_id}/{uuid.uuid4()}.pdf",
            sha256="a" * 64,
            byte_size=100,
        ),
    )
    assert result == expected
    sql = str(db.execute.call_args.args[0])
    assert "'PENDING'" in sql
    assert "'VERIFIED'" not in sql
    assert db.commit.call_count == 0


@pytest.mark.parametrize("name", ["", "../secret.pdf", "folder/file.pdf", "x" * 256])
def test_registry_rejects_unsafe_filenames(name: str) -> None:
    db = MagicMock()
    with pytest.raises(ValueError, match="filename"):
        record_pending_contract_document(
            db,
            tenant_id=uuid.uuid4(),
            contract_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            original_filename=name,
            document=IngestedPDF(object_key="legal/key.pdf", sha256="a" * 64, byte_size=100),
        )
    db.execute.assert_not_called()


@pytest.mark.parametrize(
    "failure",
    ["foreign_tenant", "foreign_contract", "bad_digest", "zero_size"],
)
def test_registry_rejects_untrusted_evidence_before_sql(failure: str) -> None:
    db = MagicMock()
    tenant, contract, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    key = f"legal/{tenant}/contracts/{contract}/{uuid.uuid4()}.pdf"
    sha, size = "a" * 64, 100
    if failure == "foreign_tenant":
        key = key.replace(str(tenant), str(uuid.uuid4()))
    elif failure == "foreign_contract":
        key = key.replace(str(contract), str(uuid.uuid4()))
    elif failure == "bad_digest":
        sha = "invalid"
    else:
        size = 0
    with pytest.raises(ValueError):
        record_pending_contract_document(
            db,
            tenant_id=tenant,
            contract_id=contract,
            actor_id=actor,
            original_filename="contract.pdf",
            document=IngestedPDF(object_key=key, sha256=sha, byte_size=size),
        )
    db.execute.assert_not_called()
