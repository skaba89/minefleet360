"""Tests des preuves de compteur, sans extrapolation de cumul."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql

from app.maintenance.preventive_meter_evidence import inspect_meter_evidence, meter_readings_query


def test_meter_query_is_scoped_to_tenant_vehicle_and_kind() -> None:
    tenant, vehicle = uuid.uuid4(), uuid.uuid4()
    sql = str(
        meter_readings_query(tenant, vehicle, "ODOMETER_KM").compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert str(tenant) in sql
    assert str(vehicle) in sql
    assert "ODOMETER_KM" in sql
    assert "ORDER BY vehicle_meter_reading.read_at DESC" in sql


def test_missing_readings_are_not_assumed_zero() -> None:
    db = MagicMock()
    db.scalars.return_value = []
    evidence = inspect_meter_evidence(db, uuid.uuid4(), uuid.uuid4(), "ODOMETER_KM")
    assert evidence.latest_value is None
    assert evidence.cumulative_verified is False
    assert evidence.has_reset is False


def test_reset_is_reported_and_raw_value_is_never_certified_cumulative() -> None:
    db = MagicMock()
    at = datetime(2026, 10, 28, 12, tzinfo=UTC)
    db.scalars.return_value = [
        SimpleNamespace(value=Decimal("125.0"), read_at=at, reset_reason=None),
        SimpleNamespace(value=Decimal("15.0"), read_at=at, reset_reason="METER_REPLACED"),
    ]
    evidence = inspect_meter_evidence(db, uuid.uuid4(), uuid.uuid4(), "ODOMETER_KM")
    assert evidence.latest_value == Decimal("125.0")
    assert evidence.latest_read_at == at
    assert evidence.has_reset is True
    assert evidence.cumulative_verified is False
