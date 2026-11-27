"""Allow explicit owner-side entitlement administration, never application writes.

Revision ID: 0080
Revises: 0079
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE POLICY iot_entitlement_owner_select ON iot_entitlement
  FOR SELECT TO mf_owner USING (tenant_id = app.current_tenant_id());
CREATE POLICY iot_entitlement_owner_insert ON iot_entitlement
  FOR INSERT TO mf_owner WITH CHECK (tenant_id = app.current_tenant_id());
CREATE POLICY iot_entitlement_owner_update ON iot_entitlement
  FOR UPDATE TO mf_owner USING (tenant_id = app.current_tenant_id())
  WITH CHECK (tenant_id = app.current_tenant_id());
"""

DOWNGRADE = r"""
DROP POLICY iot_entitlement_owner_update ON iot_entitlement;
DROP POLICY iot_entitlement_owner_insert ON iot_entitlement;
DROP POLICY iot_entitlement_owner_select ON iot_entitlement;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
