"""Verified document orchestration is tenant-scoped and audit-atomic."""

import uuid
from unittest.mock import MagicMock

import pytest

from app.legal import document_verification_workflow as workflow


def context() -> dict[str, object]:
    return {
        "tenant_id": uuid.uuid4(),
        "contract_id": uuid.uuid4(),
        "document_id": uuid.uuid4(),
        "actor_user_id": uuid.uuid4(),
        "scanner": MagicMock(),
        "store": MagicMock(),
    }


def test_verification_locks_scans_transitions_and_audits(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    db.execute.return_value.first.return_value = ("legal/key.pdf", "a" * 64, 123)
    scan = MagicMock(return_value=True)
    transition = MagicMock(return_value=True)
    audit = MagicMock()
    monkeypatch.setattr(workflow, "reverify_stored_contract_pdf", scan)
    monkeypatch.setattr(workflow, "mark_reverified_contract_document", transition)
    monkeypatch.setattr(workflow, "record", audit)
    args = context()
    assert workflow.verify_pending_contract_document(db, **args)
    assert "FOR UPDATE" in str(db.execute.call_args.args[0])
    assert "status = 'PENDING'" in str(db.execute.call_args.args[0])
    assert db.execute.call_args.args[1]["tenant"] == args["tenant_id"]
    assert scan.call_args.kwargs["tenant_id"] == args["tenant_id"]
    assert transition.call_args.kwargs["trusted_reverification_passed"] is True
    assert audit.call_args.kwargs["after"] == {"status": "VERIFIED"}
    db.commit.assert_not_called()


def test_missing_or_nonpending_row_has_no_external_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    db.execute.return_value.first.return_value = None
    scan, transition, audit = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(workflow, "reverify_stored_contract_pdf", scan)
    monkeypatch.setattr(workflow, "mark_reverified_contract_document", transition)
    monkeypatch.setattr(workflow, "record", audit)
    assert not workflow.verify_pending_contract_document(db, **context())
    scan.assert_not_called()
    transition.assert_not_called()
    audit.assert_not_called()


def test_failed_reverification_never_updates_or_audits(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    db.execute.return_value.first.return_value = ("legal/key.pdf", "a" * 64, 123)
    monkeypatch.setattr(
        workflow, "reverify_stored_contract_pdf", MagicMock(side_effect=ValueError("digest mismatch"))
    )
    transition, audit = MagicMock(), MagicMock()
    monkeypatch.setattr(workflow, "mark_reverified_contract_document", transition)
    monkeypatch.setattr(workflow, "record", audit)
    with pytest.raises(ValueError, match="mismatch"):
        workflow.verify_pending_contract_document(db, **context())
    transition.assert_not_called()
    audit.assert_not_called()


def test_concurrent_transition_failure_is_not_audited(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    db.execute.return_value.first.return_value = ("legal/key.pdf", "a" * 64, 123)
    monkeypatch.setattr(workflow, "reverify_stored_contract_pdf", MagicMock(return_value=True))
    monkeypatch.setattr(workflow, "mark_reverified_contract_document", MagicMock(return_value=False))
    audit = MagicMock()
    monkeypatch.setattr(workflow, "record", audit)
    with pytest.raises(RuntimeError, match="state changed"):
        workflow.verify_pending_contract_document(db, **context())
    audit.assert_not_called()


def test_invalid_ownership_rejected_before_database() -> None:
    db = MagicMock()
    args = context()
    args["tenant_id"] = uuid.UUID(int=0)
    with pytest.raises(ValueError, match="ownership"):
        workflow.verify_pending_contract_document(db, **args)
    db.execute.assert_not_called()
