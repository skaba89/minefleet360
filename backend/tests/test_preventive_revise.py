"""Tests des refus de révision sans permission et hors périmètre."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.errors import AppError
from app.maintenance.preventive_plan_inputs import PreventivePlanCreate
from app.maintenance.preventive_revise import revise_plan


def _body() -> PreventivePlanCreate:
    return PreventivePlanCreate(vehicle_id=uuid.uuid4(), code="REVISION-500", km_interval=500)


def test_revise_denies_without_manage_permission() -> None:
    db = MagicMock()
    auth = SimpleNamespace(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        db=db,
        scope=SimpleNamespace(permission="maintenance.preventive.read"),
    )
    with pytest.raises(AppError) as caught:
        revise_plan(auth, uuid.uuid4(), _body(), 1)
    assert caught.value.code == "PERMISSION_DENIED"
    db.commit.assert_not_called()


def test_revise_rejects_missing_plan() -> None:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    auth = SimpleNamespace(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        db=db,
        scope=SimpleNamespace(permission="maintenance.work_order.manage"),
    )
    with pytest.raises(AppError) as caught:
        revise_plan(auth, uuid.uuid4(), _body(), 1)
    assert caught.value.code == "NOT_FOUND"
    db.commit.assert_not_called()
