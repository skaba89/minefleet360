"""Garde-fous SQL des lectures internes ; sans revendication de test RLS PostgreSQL."""

import uuid
from typing import Any

from sqlalchemy import Select
from sqlalchemy.dialects import postgresql

from app.maintenance.preventive_read import dues_query, plans_query


def _sql(statement: Select[Any]) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def test_plan_read_is_scoped_to_tenant_and_vehicle() -> None:
    tenant_id, vehicle_id = uuid.uuid4(), uuid.uuid4()
    query = plans_query(tenant_id, vehicle_id, active_only=True)
    sql = _sql(query)
    assert "maintenance_plan.tenant_id =" in sql
    assert "maintenance_plan.vehicle_id =" in sql
    assert "maintenance_plan.active IS true" in sql
    assert tenant_id in query.compile().params.values()
    assert vehicle_id in query.compile().params.values()


def test_due_read_is_scoped_to_tenant_and_vehicle() -> None:
    tenant_id, vehicle_id = uuid.uuid4(), uuid.uuid4()
    query = dues_query(tenant_id, vehicle_id)
    sql = _sql(query)
    assert "maintenance_due.tenant_id =" in sql
    assert "maintenance_due.vehicle_id =" in sql
    assert tenant_id in query.compile().params.values()
    assert vehicle_id in query.compile().params.values()
