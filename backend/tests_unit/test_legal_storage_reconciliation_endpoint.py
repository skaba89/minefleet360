"""Tenant-scoped authorization for storage reconciliation endpoint."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.errors import AppError
from app.legal import router as legal_router


def test_storage_reconciliation_rejects_site_scoped_reviewer(monkeypatch: pytest.MonkeyPatch) -> None:
    store_factory = MagicMock()
    monkeypatch.setattr(legal_router, "build_private_contract_store", store_factory)
    auth = SimpleNamespace(
        tenant_id=uuid.uuid4(),
        scope=SimpleNamespace(tenant_wide=False),
        db=MagicMock(),
    )
    with pytest.raises(AppError):
        legal_router.get_contract_storage_reconciliation(auth)
    store_factory.assert_not_called()


def test_storage_reconciliation_returns_counts_only(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = SimpleNamespace(client=MagicMock(), bucket="private")
    monkeypatch.setattr(legal_router, "build_private_contract_store", lambda _settings: storage)
    monkeypatch.setattr(legal_router, "get_settings", lambda: object())
    service = MagicMock(return_value=SimpleNamespace(orphan_count=2, missing_count=1, consistent=False))
    audit_record = MagicMock()
    monkeypatch.setattr(legal_router, "record", audit_record)
    monkeypatch.setattr(legal_router, "summarize_tenant_contract_storage", service)
    tenant_id = uuid.uuid4()
    auth = SimpleNamespace(
        tenant_id=tenant_id,
        user_id=uuid.uuid4(),
        scope=SimpleNamespace(tenant_wide=True),
        db=MagicMock(),
    )
    response = legal_router.get_contract_storage_reconciliation(auth)
    assert response.model_dump() == {
        "orphan_count": 2,
        "missing_count": 1,
        "consistent": False,
    }
    assert service.call_args.kwargs["authenticated_tenant_id"] == tenant_id
    assert audit_record.call_args.kwargs["tenant_id"] == tenant_id
    assert audit_record.call_args.kwargs["after"] == {
        "orphan_count": 2,
        "missing_count": 1,
        "consistent": False,
    }
    auth.db.commit.assert_called_once()
