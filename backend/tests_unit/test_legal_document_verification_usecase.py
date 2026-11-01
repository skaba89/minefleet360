"""Verify that the document use case never bypasses ownership preflight."""

import uuid
from unittest.mock import MagicMock

import pytest

from app.legal import document_verification_usecase as usecase


def arguments() -> dict[str, object]:
    return {
        "tenant_id": uuid.uuid4(),
        "contract_id": uuid.uuid4(),
        "document_id": uuid.uuid4(),
        "actor_user_id": uuid.uuid4(),
        "review_permission_granted": True,
        "tenant_wide": True,
        "accessible_site_ids": frozenset(),
        "scanner": MagicMock(),
        "store": MagicMock(),
    }


def test_verified_usecase_passes_trusted_context(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    args = arguments()
    context = object()
    preflight = MagicMock(return_value=context)
    verification = MagicMock(return_value=True)
    monkeypatch.setattr(usecase, "load_authorized_verification_context", preflight)
    monkeypatch.setattr(usecase, "verify_authorized_contract_document", verification)
    assert usecase.verify_contract_pdf_usecase(db, **args)
    assert preflight.call_args.kwargs["tenant_id"] == args["tenant_id"]
    assert preflight.call_args.kwargs["actor_user_id"] == args["actor_user_id"]
    assert verification.call_args.kwargs["context"] is context
    assert verification.call_args.kwargs["contract_id"] == args["contract_id"]
    assert verification.call_args.kwargs["document_id"] == args["document_id"]
    db.commit.assert_not_called()


def test_denied_preflight_never_scans_or_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    args = arguments()
    monkeypatch.setattr(usecase, "load_authorized_verification_context", MagicMock(return_value=None))
    verification = MagicMock()
    monkeypatch.setattr(usecase, "verify_authorized_contract_document", verification)
    assert not usecase.verify_contract_pdf_usecase(db, **args)
    verification.assert_not_called()
    args["scanner"].scan.assert_not_called()
    args["store"].get.assert_not_called()
    db.commit.assert_not_called()


def test_failed_verification_propagates_for_transaction_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = MagicMock()
    args = arguments()
    monkeypatch.setattr(usecase, "load_authorized_verification_context", MagicMock(return_value=object()))
    monkeypatch.setattr(
        usecase,
        "verify_authorized_contract_document",
        MagicMock(side_effect=ValueError("storage integrity mismatch")),
    )
    with pytest.raises(ValueError, match="integrity"):
        usecase.verify_contract_pdf_usecase(db, **args)
    db.commit.assert_not_called()
