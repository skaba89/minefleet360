"""Contrôles de refus avant mutation d'un plan préventif."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.errors import AppError
from app.maintenance.preventive_plan_inputs import PreventivePlanSuspend
from app.maintenance.preventive_suspend import suspend_plan


def _auth(permission: str) -> SimpleNamespace:
    return SimpleNamespace(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        db=MagicMock(),
        scope=SimpleNamespace(permission=permission, covers_site=lambda _: False),
    )


def test_suspend_denies_without_manage_permission() -> None:
    auth = _auth("maintenance.preventive.read")
    with pytest.raises(AppError) as error:
        suspend_plan(auth, uuid.uuid4(), PreventivePlanSuspend(reason="Arrêt programmé"), 1)
    assert error.value.code == "PERMISSION_DENIED"
    auth.db.commit.assert_not_called()


def test_suspend_missing_plan_returns_not_found() -> None:
    auth = _auth("maintenance.work_order.manage")
    auth.db.execute.return_value.scalar_one_or_none.return_value = None
    with pytest.raises(AppError) as error:
        suspend_plan(auth, uuid.uuid4(), PreventivePlanSuspend(reason="Arrêt programmé"), 1)
    assert error.value.code == "NOT_FOUND"
    auth.db.commit.assert_not_called()


def test_suspend_rejects_out_of_scope_vehicle() -> None:
    auth = _auth("maintenance.work_order.manage")
    plan = SimpleNamespace(vehicle_id=uuid.uuid4())
    vehicle = SimpleNamespace(site_id=uuid.uuid4())
    auth.db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: plan),
        MagicMock(scalar_one_or_none=lambda: vehicle),
    ]
    with pytest.raises(AppError) as error:
        suspend_plan(auth, uuid.uuid4(), PreventivePlanSuspend(reason="Arrêt programmé"), 1)
    assert error.value.code == "NOT_FOUND"
    auth.db.commit.assert_not_called()
