"""Tests de garde du service et compilation SQL de l'anti-doublon."""

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.errors import AppError
from app.maintenance.preventive_due_candidates import DueCandidate
from app.maintenance.preventive_persist import persist_due


def _candidate() -> DueCandidate:
    return DueCandidate("DAYS", "DAYS:2026-01-01", date(2026, 1, 31), None)


def test_persist_requires_manage_permission() -> None:
    db = MagicMock()
    auth = SimpleNamespace(scope=SimpleNamespace(permission="maintenance.preventive.read"), db=db)
    with pytest.raises(AppError) as exc:
        persist_due(auth, uuid.uuid4(), _candidate())
    assert exc.value.code == "PERMISSION_DENIED"
    db.execute.assert_not_called()
    db.commit.assert_not_called()


def test_persist_rejects_unknown_plan() -> None:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    auth = SimpleNamespace(
        tenant_id=uuid.uuid4(),
        db=db,
        scope=SimpleNamespace(permission="maintenance.preventive.manage"),
    )
    with pytest.raises(AppError) as exc:
        persist_due(auth, uuid.uuid4(), _candidate())
    assert exc.value.code == "NOT_FOUND"
    db.commit.assert_not_called()


def test_persist_rejects_vehicle_outside_site() -> None:
    db = MagicMock()
    plan = SimpleNamespace(maintenance_plan_id=uuid.uuid4(), vehicle_id=uuid.uuid4())
    vehicle = SimpleNamespace(site_id=uuid.uuid4())
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: plan),
        MagicMock(scalar_one_or_none=lambda: vehicle),
    ]
    auth = SimpleNamespace(
        tenant_id=uuid.uuid4(),
        db=db,
        scope=SimpleNamespace(permission="maintenance.preventive.manage", covers_site=lambda _: False),
    )
    with pytest.raises(AppError) as exc:
        persist_due(auth, plan.maintenance_plan_id, _candidate())
    assert exc.value.code == "NOT_FOUND"
    db.commit.assert_not_called()
