"""Empreintes de secrets de traceur, jamais les secrets en clair.

Revision ID: 0024
Revises: 0023
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE fleet_gps_device_credential (
  gps_device_credential_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  gps_device_binding_id uuid NOT NULL,
  secret_fingerprint text NOT NULL,
  active_from timestamptz NOT NULL,
  revoked_at timestamptz,
  CONSTRAINT pk_fleet_gps_device_credential PRIMARY KEY (gps_device_credential_id),
  CONSTRAINT uq_fgdc_tenant_id UNIQUE (tenant_id, gps_device_credential_id),
  CONSTRAINT fk_fgdc__binding FOREIGN KEY (tenant_id, gps_device_binding_id)
    REFERENCES fleet_gps_device_binding (tenant_id, gps_device_binding_id) ON DELETE RESTRICT,
  CONSTRAINT ck_fgdc_secret CHECK (
    secret_fingerprint ~ '^[0-9a-f]{64}$'
  ),
  CONSTRAINT ck_fgdc_period CHECK (revoked_at IS NULL OR revoked_at > active_from)
);
CREATE UNIQUE INDEX uq_fgdc_active_binding
  ON fleet_gps_device_credential (tenant_id, gps_device_binding_id)
  WHERE revoked_at IS NULL;
CREATE UNIQUE INDEX uq_fgdc_fingerprint
  ON fleet_gps_device_credential (tenant_id, secret_fingerprint);
SELECT app.apply_tenant_rls('fleet_gps_device_credential', 'SELECT, INSERT, UPDATE');
"""

DOWNGRADE = r"""
DROP TABLE fleet_gps_device_credential;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
