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


def preview(auth, seconds: int = 60, vehicle: VehicleProfile | None = None):
    return mining_preview.preview_draft_route(
        auth,
        site_id=SITE,
        revision_id=REV,
        origin_id=A,
        destination_id=C,
        departure=NOW,
        horizon=NOW + timedelta(seconds=seconds),
        vehicle=vehicle,
    )


def test_preview_direct_route(auth):
    assert preview(auth) == MiningRoute((A, C), 100, 10, (DIRECT,))
    assert auth.db.execute.call_args.args[1] == {
        "tenant": TENANT,
        "site": SITE,
        "revision": REV,
        "category": None,
    }


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
VEHICLE = VehicleProfile(TENANT, SITE, CATEGORY, 40000, 4000, 3000, 12000, 100, 80)


def policy(segment_id: UUID, mass: int = 40000) -> SimpleNamespace:
    return SimpleNamespace(
        kind="policy",
        segment_id=segment_id,
        categories=[CATEGORY],
        max_gross_mass_kg=mass,
        max_speed_kmh=30,
        max_height_mm=4500,
        max_width_mm=3500,
        max_length_mm=13000,
        uphill_permille=100,
        downhill_permille=80,
    )


def test_restricted_preview_uses_same_snapshot(auth):
    policies = [policy(DIRECT, 39000), policy(FIRST), policy(SECOND)]
    auth.db.execute.return_value.all.return_value.extend(policies)
    assert preview(auth, vehicle=VEHICLE) == MiningRoute((A, B, C), 200, 40, (FIRST, SECOND))
    assert auth.db.execute.call_count == 1


def test_restricted_preview_requires_complete_policies(auth):
    assert preview(auth, vehicle=VEHICLE) is None
    incomplete = policy(DIRECT)
    incomplete.uphill_permille = None
    auth.db.execute.return_value.all.return_value.append(incomplete)
    assert preview(auth, vehicle=VEHICLE) is None


def test_restricted_preview_respects_closure_and_speed(auth):
    auth.db.execute.return_value.all.return_value.extend(
        [
            policy(DIRECT),
            policy(FIRST),
            policy(SECOND),
            SimpleNamespace(kind="closure", segment_id=DIRECT, starts_at=NOW, ends_at=None),
        ]
    )
    assert preview(auth, seconds=39, vehicle=VEHICLE) is None
    assert preview(auth, vehicle=VEHICLE) == MiningRoute((A, B, C), 200, 40, (FIRST, SECOND))


def test_foreign_vehicle_denied_before_query(auth):
    foreign = VehicleProfile(UUID(int=99), SITE, CATEGORY, 40000)
    with pytest.raises(AppError) as error:
        preview(auth, vehicle=foreign)
    assert error.value.code == "PERMISSION_DENIED"
    auth.db.execute.assert_not_called()
