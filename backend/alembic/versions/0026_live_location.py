"""Partage explicite du téléphone et provenance des positions.

Revision ID: 0026
Revises: 0025
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE fleet_gps_phone_share (
  phone_share_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  site_id uuid NOT NULL,
  user_account_id uuid NOT NULL,
  auth_session_id uuid NOT NULL,
  started_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  stopped_at timestamptz,
  last_received_at timestamptz,
  last_recorded_at timestamptz,
  CONSTRAINT uq_fgps_tenant UNIQUE (tenant_id, phone_share_id),
  CONSTRAINT fk_fgps_vehicle FOREIGN KEY (tenant_id, vehicle_id)
    REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fgps_site FOREIGN KEY (tenant_id, site_id)
    REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fgps_user FOREIGN KEY (tenant_id, user_account_id)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_fgps_period CHECK (expires_at > started_at AND
    (stopped_at IS NULL OR stopped_at >= started_at))
);
CREATE UNIQUE INDEX uq_fgps_user_active ON fleet_gps_phone_share (tenant_id, user_account_id)
  WHERE stopped_at IS NULL;
SELECT app.apply_tenant_rls('fleet_gps_phone_share', 'SELECT, INSERT, UPDATE');
ALTER TABLE fleet_gps_position ADD COLUMN source text NOT NULL DEFAULT 'TRACKER';
ALTER TABLE fleet_gps_position ADD COLUMN phone_share_id uuid;
ALTER TABLE fleet_gps_position ADD CONSTRAINT fk_fgp_phone_share
  FOREIGN KEY (tenant_id, phone_share_id)
  REFERENCES fleet_gps_phone_share (tenant_id, phone_share_id) ON DELETE RESTRICT;
ALTER TABLE fleet_gps_position ADD CONSTRAINT ck_fgp_source CHECK (
  (source = 'TRACKER' AND phone_share_id IS NULL) OR
  (source = 'PHONE' AND phone_share_id IS NOT NULL)
);
"""

DOWNGRADE = r"""
ALTER TABLE fleet_gps_position DROP CONSTRAINT ck_fgp_source;
ALTER TABLE fleet_gps_position DROP CONSTRAINT fk_fgp_phone_share;
ALTER TABLE fleet_gps_position DROP COLUMN phone_share_id;
ALTER TABLE fleet_gps_position DROP COLUMN source;
DROP TABLE fleet_gps_phone_share;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
