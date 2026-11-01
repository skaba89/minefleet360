"""Document verification API must fail closed and commit only on success."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.errors import AppError
from app.legal import router as legal_router


def test_document_verification_commits_only_after_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    auth = SimpleNamespace(
        db=db,
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        scope=SimpleNamespace(tenant_wide=True, site_ids=set()),
    )
    monkeypatch.setattr(
        legal_router,
        "get_settings",
        lambda: SimpleNamespace(legal_malware_scan_enabled=True, legal_object_storage_enabled=True),
    )
    monkeypatch.setattr(legal_router, "build_contract_malware_scanner", lambda _settings: object())
    monkeypatch.setattr(legal_router, "build_private_contract_store", lambda _settings: object())
    service = MagicMock(return_value=True)
    monkeypatch.setattr(legal_router, "verify_contract_pdf_usecase", service)
    doc_id = uuid.uuid4()
    assert legal_router.verify_contract_document(uuid.uuid4(), doc_id, auth) == {
        "document_id": str(doc_id),
        "status": "VERIFIED",
    }
    assert service.call_args.kwargs["tenant_id"] == auth.tenant_id
    db.commit.assert_called_once()


def test_document_verification_denied_does_not_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    auth = SimpleNamespace(
        db=db,
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        scope=SimpleNamespace(tenant_wide=True, site_ids=set()),
    )
    monkeypatch.setattr(
        legal_router,
        "get_settings",
        lambda: SimpleNamespace(legal_malware_scan_enabled=True, legal_object_storage_enabled=True),
    )
    monkeypatch.setattr(legal_router, "build_contract_malware_scanner", lambda _settings: object())
    monkeypatch.setattr(legal_router, "build_private_contract_store", lambda _settings: object())
    monkeypatch.setattr(legal_router, "verify_contract_pdf_usecase", MagicMock(return_value=False))
    with pytest.raises(AppError):
        legal_router.verify_contract_document(uuid.uuid4(), uuid.uuid4(), auth)
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_missing_document_returns_404_before_storage_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = MagicMock()
    db.scalar.return_value = False
    auth = SimpleNamespace(
        db=db,
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        scope=SimpleNamespace(tenant_wide=True, site_ids=set()),
    )
    settings = MagicMock()
    service = MagicMock()
    monkeypatch.setattr(legal_router, "get_settings", settings)
    monkeypatch.setattr(legal_router, "verify_contract_pdf_usecase", service)
    with pytest.raises(AppError) as caught:
        legal_router.verify_contract_document(uuid.uuid4(), uuid.uuid4(), auth)
    assert caught.value.code == "NOT_FOUND"
    settings.assert_not_called()
    service.assert_not_called()
    db.commit.assert_not_called()
