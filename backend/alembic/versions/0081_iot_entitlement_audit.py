"""Permit owner-side entitlement audit and customer lookup under forced RLS.

Revision ID: 0081
Revises: 0080
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE POLICY iot_owner_customer_lookup ON tenant
  FOR SELECT TO mf_owner
  USING (tenant_id = app.current_tenant_id() AND kind = 'CUSTOMER');
CREATE POLICY iot_owner_audit_insert ON audit_event
  FOR INSERT TO mf_owner
  WITH CHECK (
    tenant_id = app.current_tenant_id()
    AND actor_kind = 'SYSTEM'
    AND action = 'iot.entitlement.change'
    AND entity_type = 'iot_entitlement'
    AND entity_id = tenant_id
    AND outcome = 'SUCCESS'
  );
"""

DOWNGRADE = r"""
DROP POLICY iot_owner_audit_insert ON audit_event;
DROP POLICY iot_owner_customer_lookup ON tenant;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
