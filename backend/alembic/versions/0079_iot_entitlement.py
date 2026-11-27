"""Tenant-scoped IoT entitlement, disabled by absence of a grant.

Revision ID: 0079
Revises: 0078
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE iot_entitlement (
  tenant_id uuid PRIMARY KEY REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  provisioning_enabled boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now()
);
SELECT app.apply_tenant_rls('iot_entitlement', 'SELECT');
"""

DOWNGRADE = r"""
DROP TABLE iot_entitlement;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
