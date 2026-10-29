"""Séquences monotones de messages GPS par traceur pour limiter les rejouements.

Revision ID: 0025
Revises: 0024
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE fleet_gps_device_sequence (
  tenant_id uuid NOT NULL,
  gps_device_binding_id uuid NOT NULL,
  last_sequence bigint NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_fgds PRIMARY KEY (tenant_id, gps_device_binding_id),
  CONSTRAINT fk_fgds__binding FOREIGN KEY (tenant_id, gps_device_binding_id)
    REFERENCES fleet_gps_device_binding (tenant_id, gps_device_binding_id) ON DELETE RESTRICT,
  CONSTRAINT ck_fgds_sequence CHECK (last_sequence BETWEEN 0 AND 9223372036854775807)
);
SELECT app.apply_tenant_rls('fleet_gps_device_sequence', 'SELECT, INSERT, UPDATE');
"""

DOWNGRADE = r"""
DROP TABLE fleet_gps_device_sequence;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
