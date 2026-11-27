from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.core.errors import AppError
from app.dispatch import mining_closure_read

TENANT, SITE, REV, SEGMENT = (UUID(int=i) for i in range(1, 5))
NOW = datetime(2026, 11, 27, tzinfo=UTC)


@pytest.fixture
def auth(monkeypatch):
    auth = MagicMock()
    auth.tenant_id = TENANT
    auth.principal.mfa_enrollment_pending = False
    scope = MagicMock()
    scope.covers_site.return_value = True
    monkeypatch.setattr(mining_closure_read, "evaluate", lambda *_: scope)
    monkeypatch.setattr(
        mining_closure_read,
        "site_in_scope",
        lambda *_: SimpleNamespace(tenant_id=TENANT, status="ACTIVE"),
    )
    revision = MagicMock()
    revision.scalar_one_or_none.return_value = REV
    result = MagicMock()
    result.all.return_value = [SimpleNamespace(segment_id=SEGMENT, starts_at=NOW, ends_at=None)]
    auth.db.execute.side_effect = [revision, result]
    return auth


def test_complete_snapshot(auth):
    result = mining_closure_read.load_closures(auth, SITE, REV)
    assert result == [mining_closure_read.ClosureRow(SEGMENT, NOW, None)]
    for call in auth.db.execute.call_args_list:
        assert call.args[1] == {"tenant": TENANT, "site": SITE, "revision": REV, "limit": 1001}


def test_permission_denied_before_query(auth, monkeypatch):
    monkeypatch.setattr(mining_closure_read, "evaluate", lambda *_: None)
    with pytest.raises(AppError):
        mining_closure_read.load_closures(auth, SITE, REV)
    auth.db.execute.assert_not_called()


def test_mfa_required_before_query(auth):
    auth.principal.mfa_enrollment_pending = True
    with pytest.raises(AppError):
        mining_closure_read.load_closures(auth, SITE, REV)
    auth.db.execute.assert_not_called()


def test_overflow_never_returns_partial_snapshot(auth):
    revision = MagicMock()
    revision.scalar_one_or_none.return_value = REV
    result = MagicMock()
    result.all.return_value = [object(), object()]
    auth.db.execute.side_effect = [revision, result]
    with pytest.raises(AppError):
        mining_closure_read.load_closures(auth, SITE, REV, limit=1)


def test_missing_revision_stops_read(auth):
    revision = MagicMock()
    revision.scalar_one_or_none.return_value = None
    auth.db.execute.side_effect = [revision]
    with pytest.raises(AppError):
        mining_closure_read.load_closures(auth, SITE, REV)
    assert auth.db.execute.call_count == 1
