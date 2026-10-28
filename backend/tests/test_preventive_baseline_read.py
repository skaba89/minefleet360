"""Contrat de récupération du dernier entretien préventif clôturé."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql

from app.maintenance.preventive_baseline_read import (
    completed_preventive_orders_query,
    load_verified_service_baseline,
)


def test_last_service_query_requires_tenant_vehicle_and_closed_preventive() -> None:
    tenant_id, vehicle_id = uuid.uuid4(), uuid.uuid4()
    sql = str(
        completed_preventive_orders_query(tenant_id, vehicle_id).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert str(tenant_id) in sql
    assert str(vehicle_id) in sql
    assert "work_order.kind = 'PREVENTIVE'" in sql
    assert "work_order.status = 'CLOSED'" in sql
    assert "work_order.closed_at IS NOT NULL" in sql
    assert "ORDER BY work_order.closed_at DESC" in sql
    assert "LIMIT 1" in sql


def test_closed_preventive_date_does_not_invent_meter_values() -> None:
    db = MagicMock()
    db.scalars.return_value.first.return_value = SimpleNamespace(
        closed_at=datetime(2026, 10, 28, 21, 30, tzinfo=UTC)
    )
    result = load_verified_service_baseline(db, uuid.uuid4(), uuid.uuid4())
    assert result.serviced_on.isoformat() == "2026-10-28"
    assert result.cumulative_km is None
    assert result.cumulative_hours is None


def test_missing_closed_preventive_keeps_baseline_unknown() -> None:
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    result = load_verified_service_baseline(db, uuid.uuid4(), uuid.uuid4())
    assert result.serviced_on is None
    assert result.cumulative_km is None
    assert result.cumulative_hours is None
