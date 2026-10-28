"""Garde de permission et refus pour une échéance introuvable."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.errors import AppError
from app.maintenance.preventive_schedule import schedule_preventive_order


def test_schedule_requires_preventive_manage_permission() -> None:
    db = MagicMock()
    auth = SimpleNamespace(db=db, scope=SimpleNamespace(permission="maintenance.preventive.read"))
    with pytest.raises(AppError) as error:
        schedule_preventive_order(auth, uuid.uuid4())
    assert error.value.code == "PERMISSION_DENIED"
    db.execute.assert_not_called()
    db.commit.assert_not_called()


def test_schedule_missing_due_does_not_write() -> None:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    auth = SimpleNamespace(
        db=db,
        tenant_id=uuid.uuid4(),
        scope=SimpleNamespace(permission="maintenance.preventive.manage"),
    )
    with pytest.raises(AppError) as error:
        schedule_preventive_order(auth, uuid.uuid4())
    assert error.value.code == "NOT_FOUND"
    db.commit.assert_not_called()


def test_schedule_replay_returns_existing_order_without_commit() -> None:
    order_id = uuid.uuid4()
    due = SimpleNamespace(work_order_id=order_id, status="SCHEDULED", vehicle_id=uuid.uuid4())
    vehicle = SimpleNamespace(site_id=uuid.uuid4())
    db = MagicMock()
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: due),
        MagicMock(scalar_one_or_none=lambda: vehicle),
    ]
    auth = SimpleNamespace(
        db=db,
        tenant_id=uuid.uuid4(),
        scope=SimpleNamespace(permission="maintenance.preventive.manage", covers_site=lambda _: True),
    )
    assert schedule_preventive_order(auth, uuid.uuid4()) == order_id
    db.commit.assert_not_called()


@pytest.mark.parametrize("active", [False, None])
def test_schedule_refuses_inactive_or_missing_plan(active: bool | None) -> None:
    due = SimpleNamespace(
        maintenance_plan_id=uuid.uuid4(),
        vehicle_id=uuid.uuid4(),
        work_order_id=None,
        status="DUE",
    )
    vehicle = SimpleNamespace(site_id=uuid.uuid4())
    plan = None if active is None else SimpleNamespace(active=active)
    db = MagicMock()
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: due),
        MagicMock(scalar_one_or_none=lambda: vehicle),
        MagicMock(scalar_one_or_none=lambda: plan),
    ]
    auth = SimpleNamespace(
        db=db,
        tenant_id=uuid.uuid4(),
        scope=SimpleNamespace(permission="maintenance.preventive.manage", covers_site=lambda _: True),
    )
    with pytest.raises(AppError) as error:
        schedule_preventive_order(auth, uuid.uuid4())
    assert error.value.code == "STATE_TRANSITION_INVALID"
    db.commit.assert_not_called()
