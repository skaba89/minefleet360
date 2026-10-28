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


def test_schedule_creates_preventive_order_and_commits_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """La création associe l'OT et l'échéance dans un unique commit."""
    from app.maintenance import preventive_schedule

    due_id, vehicle_id, order_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    due = SimpleNamespace(
        maintenance_plan_id=uuid.uuid4(),
        vehicle_id=vehicle_id,
        work_order_id=None,
        status="DUE",
    )
    vehicle = SimpleNamespace(site_id=uuid.uuid4())
    plan = SimpleNamespace(active=True)
    order = SimpleNamespace(work_order_id=order_id, kind="CORRECTIVE")
    db = MagicMock()
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: due),
        MagicMock(scalar_one_or_none=lambda: vehicle),
        MagicMock(scalar_one_or_none=lambda: plan),
        MagicMock(scalar_one=lambda: order),
    ]
    auth = SimpleNamespace(
        db=db,
        tenant_id=uuid.uuid4(),
        scope=SimpleNamespace(permission="maintenance.preventive.manage", covers_site=lambda _: True),
    )
    create_order = MagicMock(return_value=SimpleNamespace(work_order_id=order_id))
    monkeypatch.setattr(preventive_schedule, "_create_work_order_uncommitted", create_order)

    assert schedule_preventive_order(auth, due_id) == order_id
    create_order.assert_called_once()
    assert order.kind == "PREVENTIVE"
    assert due.work_order_id == order_id
    assert due.status == "SCHEDULED"
    db.flush.assert_called_once_with()
    db.commit.assert_called_once_with()


def test_schedule_flush_failure_never_commits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Une erreur de flush est propagée ; aucun commit ne doit suivre."""
    from app.maintenance import preventive_schedule

    vehicle_id, order_id = uuid.uuid4(), uuid.uuid4()
    due = SimpleNamespace(
        maintenance_plan_id=uuid.uuid4(), vehicle_id=vehicle_id, work_order_id=None, status="DUE"
    )
    order = SimpleNamespace(work_order_id=order_id, kind="CORRECTIVE")
    db = MagicMock()
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: due),
        MagicMock(scalar_one_or_none=lambda: SimpleNamespace(site_id=uuid.uuid4())),
        MagicMock(scalar_one_or_none=lambda: SimpleNamespace(active=True)),
        MagicMock(scalar_one=lambda: order),
    ]
    db.flush.side_effect = RuntimeError("database flush failed")
    auth = SimpleNamespace(
        db=db, tenant_id=uuid.uuid4(),
        scope=SimpleNamespace(permission="maintenance.preventive.manage", covers_site=lambda _: True),
    )
    monkeypatch.setattr(
        preventive_schedule,
        "_create_work_order_uncommitted",
        MagicMock(return_value=SimpleNamespace(work_order_id=order_id)),
    )

    with pytest.raises(RuntimeError, match="database flush failed"):
        schedule_preventive_order(auth, uuid.uuid4())
    db.commit.assert_not_called()
