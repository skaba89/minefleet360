"""Résolution GPS : refus des associations absentes et révoquées."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.fleet.gps_binding_lookup import resolve_gps_binding

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)


def _args() -> dict[str, object]:
    return {
        "tenant_id": uuid.uuid4(),
        "vehicle_id": uuid.uuid4(),
        "site_id": uuid.uuid4(),
        "device_id": "gps-001",
        "recorded_at": NOW,
    }


def test_unknown_device_returns_none() -> None:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    assert resolve_gps_binding(db, **_args()) is None


def test_matching_device_is_returned() -> None:
    db = MagicMock()
    args = _args()
    device = SimpleNamespace(**args, active_from=NOW, revoked_at=None)
    db.execute.return_value.scalar_one_or_none.return_value = device
    assert resolve_gps_binding(db, **args) is device


def test_revoked_device_is_rejected() -> None:
    db = MagicMock()
    args = _args()
    device = SimpleNamespace(**args, active_from=NOW, revoked_at=NOW)
    db.execute.return_value.scalar_one_or_none.return_value = device
    assert resolve_gps_binding(db, **args) is None


def test_naive_timestamp_fails_before_database() -> None:
    db = MagicMock()
    args = _args()
    args["recorded_at"] = NOW.replace(tzinfo=None)
    assert resolve_gps_binding(db, **args) is None
    db.execute.assert_not_called()
