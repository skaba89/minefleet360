"""Tests du calcul par lot avant automatisation des échéances."""

import uuid
from datetime import date
from decimal import Decimal

from app.maintenance.preventive import CurrentMeters, ServiceBaseline, ServiceRule
from app.maintenance.preventive_batch import PlanSnapshot, preview_due_batch


def _snapshot(*, active: bool = True, reliable: bool = True) -> PlanSnapshot:
    return PlanSnapshot(
        tenant_id=uuid.uuid4(),
        plan_id=uuid.uuid4(),
        vehicle_id=uuid.uuid4(),
        rule=ServiceRule(km_interval=Decimal("100.0"), days_interval=30),
        baseline=ServiceBaseline(serviced_on=date(2026, 1, 1), cumulative_km=Decimal("1000.0")),
        meters=CurrentMeters(cumulative_km=Decimal("1200.0"), km_reliable=reliable),
        active=active,
    )


def test_batch_deduplicates_same_plan_and_cycle() -> None:
    snapshot = _snapshot()
    due = preview_due_batch((snapshot, snapshot), date(2026, 3, 1))
    assert len(due) == 1
    assert due[0].plan_id == snapshot.plan_id
    assert due[0].candidate.trigger_kind == "DAYS"


def test_batch_skips_inactive_plans_and_keeps_tenants_separate() -> None:
    first, second = _snapshot(), _snapshot()
    due = preview_due_batch((first, _snapshot(active=False), second), date(2026, 3, 1))
    assert {row.tenant_id for row in due} == {first.tenant_id, second.tenant_id}


def test_batch_never_invents_missing_meter_values() -> None:
    snapshot = PlanSnapshot(
        tenant_id=uuid.uuid4(),
        plan_id=uuid.uuid4(),
        vehicle_id=uuid.uuid4(),
        rule=ServiceRule(km_interval=Decimal("50.0")),
        baseline=ServiceBaseline(cumulative_km=Decimal("1000.0")),
        meters=CurrentMeters(cumulative_km=Decimal("1200.0"), km_reliable=False),
    )
    assert preview_due_batch((snapshot,), date(2026, 3, 1)) == ()


def test_batch_is_stable_regardless_of_input_order() -> None:
    first, second = _snapshot(), _snapshot()
    assert preview_due_batch((first, second), date(2026, 3, 1)) == preview_due_batch(
        (second, first), date(2026, 3, 1)
    )
