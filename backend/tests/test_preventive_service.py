"""Tests de garde de portée ; tests RLS réels requis avant exposition API."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.errors import AppError
from app.maintenance.preventive_service import _ensure_vehicle_in_scope


def test_unknown_vehicle_is_not_found() -> None:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    auth = SimpleNamespace(tenant_id=uuid.uuid4(), db=db, scope=MagicMock())
    with pytest.raises(AppError) as error:
        _ensure_vehicle_in_scope(auth, uuid.uuid4())
    assert error.value.code == "NOT_FOUND"


def test_out_of_site_scope_is_not_found() -> None:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = SimpleNamespace(site_id=uuid.uuid4())
    scope = MagicMock()
    scope.covers_site.return_value = False
    auth = SimpleNamespace(tenant_id=uuid.uuid4(), db=db, scope=scope)
    with pytest.raises(AppError) as error:
        _ensure_vehicle_in_scope(auth, uuid.uuid4())
    assert error.value.code == "NOT_FOUND"
