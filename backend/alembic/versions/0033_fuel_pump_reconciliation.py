"""Rattachement des sorties carburant aux pompes.

Revision ID: 0033
Revises: 0032
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE fuel_issue ADD COLUMN fuel_pump_id uuid;
ALTER TABLE fuel_issue ADD CONSTRAINT fk_fuel_issue_pump
  FOREIGN KEY (tenant_id, fuel_pump_id, site_id)
  REFERENCES fuel_pump (tenant_id, fuel_pump_id, site_id) ON DELETE RESTRICT;
CREATE INDEX ix_fuel_issue_pump_time
  ON fuel_issue (tenant_id, fuel_pump_id, requested_at)
  WHERE fuel_pump_id IS NOT NULL;
"""

DOWNGRADE = r"""
DROP INDEX ix_fuel_issue_pump_time;
ALTER TABLE fuel_issue DROP CONSTRAINT fk_fuel_issue_pump;
ALTER TABLE fuel_issue DROP COLUMN fuel_pump_id;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
