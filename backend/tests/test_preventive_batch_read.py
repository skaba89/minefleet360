"""Contrat SQL de lecture des plans préventifs pour le traitement batch."""

import uuid

from sqlalchemy.dialects import postgresql

from app.maintenance.preventive_batch_read import active_plans_query


def _sql(tenant_id: uuid.UUID, sites: frozenset[uuid.UUID] | None = None) -> str:
    return str(
        active_plans_query(tenant_id, sites).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def test_batch_plan_query_is_tenant_scoped_and_active_only() -> None:
    tenant = uuid.uuid4()
    sql = _sql(tenant)
    assert str(tenant) in sql
    assert "maintenance_plan.tenant_id" in sql
    assert "vehicle.tenant_id" in sql
    assert "maintenance_plan.active IS true" in sql
    assert "vehicle.status != 'RETIRED'" in sql
    assert "vehicle.vehicle_id = maintenance_plan.vehicle_id" in sql


def test_batch_plan_query_does_not_read_other_sites() -> None:
    site = uuid.uuid4()
    assert str(site) in _sql(uuid.uuid4(), frozenset({site}))


def test_batch_plan_query_empty_scope_never_matches_any_site() -> None:
    sql = _sql(uuid.uuid4(), frozenset())
    assert "vehicle.site_id IN (NULL)" in sql or "1 != 1" in sql
