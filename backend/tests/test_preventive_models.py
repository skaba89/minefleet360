"""Contrat ORM : les colonnes restent alignées sur la migration 0019."""

from sqlalchemy import DateTime, Numeric
from sqlalchemy.dialects.postgresql import UUID

from app.maintenance.preventive_models import MaintenanceDue, MaintenancePlan


def test_plan_columns_match_migration_0019() -> None:
    table = MaintenancePlan.__table__
    assert table.name == "maintenance_plan"
    assert set(table.columns.keys()) == {
        "maintenance_plan_id",
        "tenant_id",
        "vehicle_id",
        "code",
        "version",
        "km_interval",
        "hours_interval",
        "days_interval",
        "active",
        "suspension_reason",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "row_version",
    }
    assert isinstance(table.c.tenant_id.type, UUID)
    assert isinstance(table.c.km_interval.type, Numeric)
    assert table.c.km_interval.type.scale == 1


def test_due_columns_match_migration_0019() -> None:
    table = MaintenanceDue.__table__
    assert table.name == "maintenance_due"
    assert set(table.columns.keys()) == {
        "maintenance_due_id",
        "tenant_id",
        "maintenance_plan_id",
        "vehicle_id",
        "trigger_kind",
        "trigger_key",
        "status",
        "due_on",
        "due_meter",
        "evaluated_at",
        "work_order_id",
        "created_at",
    }
    assert isinstance(table.c.tenant_id.type, UUID)
    assert isinstance(table.c.evaluated_at.type, DateTime)
    assert table.c.evaluated_at.type.timezone
