"""Associations GPS enregistrées avec isolement tenant et révocation.

Revision ID: 0023
Revises: 0022
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE fleet_gps_device_binding (
  gps_device_binding_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  site_id uuid NOT NULL,
  device_id text NOT NULL,
  active_from timestamptz NOT NULL,
  revoked_at timestamptz,
  CONSTRAINT pk_fleet_gps_device_binding PRIMARY KEY (gps_device_binding_id),
  CONSTRAINT uq_fgdb_tenant_binding UNIQUE (tenant_id, gps_device_binding_id),
  CONSTRAINT fk_fgdb__vehicle FOREIGN KEY (tenant_id, vehicle_id)
    REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fgdb__site FOREIGN KEY (tenant_id, site_id)
    REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT ck_fgdb_device CHECK (char_length(btrim(device_id)) BETWEEN 1 AND 120),
  CONSTRAINT ck_fgdb_period CHECK (revoked_at IS NULL OR revoked_at > active_from)
);
CREATE UNIQUE INDEX uq_fgdb_one_active_device
  ON fleet_gps_device_binding (tenant_id, device_id)
  WHERE revoked_at IS NULL;
CREATE UNIQUE INDEX uq_fgdb_one_active_vehicle
  ON fleet_gps_device_binding (tenant_id, vehicle_id)
  WHERE revoked_at IS NULL;
CREATE INDEX ix_fgdb_vehicle ON fleet_gps_device_binding (tenant_id, vehicle_id);
SELECT app.apply_tenant_rls('fleet_gps_device_binding', 'SELECT, INSERT, UPDATE');
"""

DOWNGRADE = r"""
DROP TABLE fleet_gps_device_binding;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
