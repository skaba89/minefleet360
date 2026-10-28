"""Tests de refus de service (pas un substitut aux tests DB RLS)."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.errors import AppError
from app.maintenance.preventive_plan_inputs import PreventivePlanCreate
from app.maintenance.preventive_write import create_plan


def _body() -> PreventivePlanCreate:
    return PreventivePlanCreate(vehicle_id=uuid.uuid4(), code="REVISION-500", km_interval=500)


def test_create_requires_manage_permission() -> None:
    db = MagicMock()
    auth = SimpleNamespace(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        db=db,
        scope=SimpleNamespace(permission="maintenance.preventive.read"),
    )
    with pytest.raises(AppError) as caught:
        create_plan(auth, _body())
    assert caught.value.code == "PERMISSION_DENIED"
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_create_refuses_vehicle_outside_site() -> None:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = SimpleNamespace(site_id=uuid.uuid4())
    auth = SimpleNamespace(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        db=db,
        scope=SimpleNamespace(permission="maintenance.work_order.manage", covers_site=lambda _: False),
    )
    with pytest.raises(AppError) as caught:
        create_plan(auth, _body())
    assert caught.value.code == "NOT_FOUND"
    db.add.assert_not_called()
    db.commit.assert_not_called()
