from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.dispatch import smart_pool

TENANT = UUID(int=1)
SITE = UUID(int=2)
NOW = datetime(2026, 11, 26, tzinfo=UTC)


def test_pool_rejects_missing_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    auth = MagicMock(spec=Authorized)
    monkeypatch.setattr(smart_pool, "evaluate", lambda *_: None)
    with pytest.raises(AppError):
        smart_pool.eligible_pool(auth, SITE)
    auth.db.execute.assert_not_called()


def test_pool_filters_blocked_assignments(monkeypatch: pytest.MonkeyPatch) -> None:
    auth = MagicMock(spec=Authorized)
    auth.tenant_id = TENANT
    auth.clock.now.return_value = NOW
    scope = MagicMock()
    scope.covers_site.return_value = True
    monkeypatch.setattr(smart_pool, "evaluate", lambda *_: scope)
    monkeypatch.setattr(
        smart_pool, "site_in_scope", lambda *_: SimpleNamespace(tenant_id=TENANT, status="ACTIVE")
    )
    rows = [
        SimpleNamespace(
            vehicle_assignment_id=UUID(int=i),
            site_id=SITE,
            vehicle_id=UUID(int=i + 10),
            driver_id=UUID(int=i + 20),
            status="ACTIVE",
            valid_from=NOW,
            valid_to=None,
        )
        for i in (3, 4)
    ]
    auth.db.execute.return_value.scalars.return_value = rows
    monkeypatch.setattr(
        smart_pool,
        "running_blockers",
        lambda _db, facts, _now: ["BLOCKED"] if facts.vehicle_assignment_id == UUID(int=3) else [],
    )
    result = smart_pool.eligible_pool(auth, SITE)
    assert [facts.vehicle_assignment_id for facts in result] == [UUID(int=4)]
    auth.db.commit.assert_not_called()
