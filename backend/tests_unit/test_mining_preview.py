from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.core.errors import AppError
from app.dispatch import mining_preview
from app.dispatch.mining_restrictions import VehicleProfile
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


CATEGORY = UUID(int=20)
PROFILE = VehicleProfile(TENANT, SITE, CATEGORY, 40000, 4000, 3000, 12000, 100, 100)


def policy(segment_id: UUID, mass: int = 40000) -> SimpleNamespace:
    return SimpleNamespace(
        kind="policy",
        segment_id=segment_id,
        categories=[CATEGORY],
        max_gross_mass_kg=mass,
        max_speed_kmh=30,
        max_height_mm=4000,
        max_width_mm=3000,
        max_length_mm=12000,
        uphill_permille=80,
        downhill_permille=80,
    )


def restricted_preview(auth, profile: VehicleProfile = PROFILE):
    return mining_preview.preview_draft_route(
        auth,
        site_id=SITE,
        revision_id=REV,
        origin_id=A,
        destination_id=C,
        departure=NOW,
        horizon=NOW + timedelta(seconds=60),
        vehicle=profile,
    )


def test_restricted_preview_uses_compatible_detour(auth):
    auth.db.execute.return_value.all.return_value.extend(
        [policy(DIRECT, 39999), policy(FIRST), policy(SECOND)]
    )
    assert restricted_preview(auth) == MiningRoute((A, B, C), 200, 40, (FIRST, SECOND))
    assert auth.db.execute.call_count == 1


def test_restricted_preview_missing_policies_fails_closed(auth):
    assert restricted_preview(auth) is None


def test_restricted_preview_respects_closure_and_grade(auth):
    direct = policy(DIRECT)
    direct.uphill_permille = 101
    auth.db.execute.return_value.all.return_value.extend(
        [
            direct,
            policy(FIRST),
            policy(SECOND),
            SimpleNamespace(kind="closure", segment_id=SECOND, starts_at=NOW, ends_at=None),
        ]
    )
    assert restricted_preview(auth) is None


def test_restricted_preview_foreign_profile_rejected(auth):
    with pytest.raises(AppError) as error:
        restricted_preview(auth, replace(PROFILE, tenant_id=REV))
    assert error.value.code == "PERMISSION_DENIED"
    auth.db.execute.assert_not_called()


def test_restricted_preview_policy_overflow(auth):
    auth.db.execute.return_value.all.return_value.extend([policy(DIRECT)] * 1001)
    with pytest.raises(AppError) as error:
        restricted_preview(auth)
    assert error.value.code == "CONFLICT"
