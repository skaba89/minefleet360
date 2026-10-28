"""Validation des requêtes avant ajout de routes de mutation."""

import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.maintenance.preventive_plan_inputs import PreventivePlanCreate, PreventivePlanSuspend


def _valid() -> dict[str, object]:
    return {"vehicle_id": uuid.uuid4(), "code": "ENTRETIEN-500", "km_interval": "500.0"}


def test_plan_accepts_meter_interval() -> None:
    plan = PreventivePlanCreate.model_validate(_valid())
    assert plan.km_interval == Decimal("500.0")


def test_plan_rejects_missing_intervals() -> None:
    data = _valid()
    del data["km_interval"]
    with pytest.raises(ValidationError):
        PreventivePlanCreate.model_validate(data)


@pytest.mark.parametrize("value", ["0", "-2", "NaN", "Infinity", "1.234"])
def test_plan_rejects_invalid_meter_intervals(value: str) -> None:
    data = _valid()
    data["km_interval"] = value
    with pytest.raises(ValidationError):
        PreventivePlanCreate.model_validate(data)


def test_plan_rejects_client_supplied_tenant_id() -> None:
    data = _valid()
    data["tenant_id"] = uuid.uuid4()
    with pytest.raises(ValidationError):
        PreventivePlanCreate.model_validate(data)


def test_plan_rejects_unknown_or_unsafe_code() -> None:
    data = _valid()
    data["code"] = "ENTRETIEN 500"
    with pytest.raises(ValidationError):
        PreventivePlanCreate.model_validate(data)


def test_suspension_reason_required() -> None:
    with pytest.raises(ValidationError):
        PreventivePlanSuspend(reason=" ")
