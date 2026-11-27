from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.core.errors import AppError
from app.dispatch import mining_preview
from app.dispatch.mining_routes import MiningRoute

TENANT, SITE, REV, A, B, C, DIRECT, FIRST, SECOND = (UUID(int=i) for i in range(1, 10))
NOW = datetime(2026, 11, 27, tzinfo=UTC)


def road(segment_id: UUID, origin: UUID, destination: UUID, duration: int) -> SimpleNamespace:
    return SimpleNamespace(
        kind="road",
        segment_id=segment_id,
        origin_id=origin,
        destination_id=destination,
        distance_m=100,
        duration_seconds=duration,
    )


@pytest.fixture
def auth(monkeypatch):
    auth = MagicMock()
    auth.tenant_id = TENANT
    auth.principal.tenant_kind = "CUSTOMER"
    auth.principal.mfa_enrollment_pending = False
    scope = MagicMock()
    scope.covers_site.return_value = True
    monkeypatch.setattr(mining_preview, "evaluate", lambda *_: scope)
    auth.db.execute.return_value.all.return_value = [
        SimpleNamespace(kind="revision"),
        road(DIRECT, A, C, 10),
        road(FIRST, A, B, 20),
        road(SECOND, B, C, 20),
    ]
    return auth


def preview(auth, seconds: int = 60):
    return mining_preview.preview_draft_route(
        auth,
        site_id=SITE,
        revision_id=REV,
        origin_id=A,
        destination_id=C,
        departure=NOW,
        horizon=NOW + timedelta(seconds=seconds),
    )


def test_preview_direct_route(auth):
    assert preview(auth) == MiningRoute((A, C), 100, 10, (DIRECT,))
    assert auth.db.execute.call_args.args[1] == {"tenant": TENANT, "site": SITE, "revision": REV}


def test_closure_in_same_snapshot(auth):
    auth.db.execute.return_value.all.return_value.append(
        SimpleNamespace(kind="closure", segment_id=DIRECT, starts_at=NOW, ends_at=None)
    )
    assert preview(auth) == MiningRoute((A, B, C), 200, 40, (FIRST, SECOND))
    assert auth.db.execute.call_count == 1


def test_authorization_failure_stops_graph_read(auth, monkeypatch):
    monkeypatch.setattr(mining_preview, "evaluate", lambda *_: None)
    with pytest.raises(AppError) as error:
        preview(auth)
    assert error.value.code == "PERMISSION_DENIED"
    auth.db.execute.assert_not_called()


def test_graph_overflow_rejected(auth):
    auth.db.execute.return_value.all.return_value = [
        SimpleNamespace(kind="revision"),
        *[SimpleNamespace(kind="road")] * 1001,
    ]
    with pytest.raises(AppError) as error:
        preview(auth)
    assert error.value.code == "CONFLICT"


def test_closure_overflow_rejected(auth):
    auth.db.execute.return_value.all.return_value = [
        SimpleNamespace(kind="revision"),
        *[SimpleNamespace(kind="closure")] * 1001,
    ]
    with pytest.raises(AppError) as error:
        preview(auth)
    assert error.value.code == "CONFLICT"


def test_missing_revision_rejected(auth):
    auth.db.execute.return_value.all.return_value = []
    with pytest.raises(AppError) as error:
        preview(auth)
    assert error.value.code == "NOT_FOUND"


def test_route_beyond_planning_window_rejected(auth):
    assert preview(auth, seconds=5) is None
