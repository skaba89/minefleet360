"""Historique GPS append-only, isolé par société et lié au parc.

Revision ID: 0022
Revises: 0021
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE fleet_gps_position (
  gps_position_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  site_id uuid NOT NULL,
  device_id text NOT NULL,
  latitude double precision NOT NULL,
  longitude double precision NOT NULL,
  speed_kmh double precision,
  accuracy_m double precision,
  recorded_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_fleet_gps_position PRIMARY KEY (gps_position_id),
  CONSTRAINT uq_fgp_tenant_id UNIQUE (tenant_id, gps_position_id),
  CONSTRAINT uq_fgp_device_time UNIQUE (tenant_id, device_id, recorded_at),
  CONSTRAINT fk_fgp__vehicle FOREIGN KEY (tenant_id, vehicle_id)
    REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fgp__site FOREIGN KEY (tenant_id, site_id)
    REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT ck_fgp_device CHECK (char_length(btrim(device_id)) BETWEEN 1 AND 120),
  CONSTRAINT ck_fgp_lat CHECK (isfinite(latitude) AND latitude BETWEEN -90 AND 90),
  CONSTRAINT ck_fgp_lon CHECK (isfinite(longitude) AND longitude BETWEEN -180 AND 180),
  CONSTRAINT ck_fgp_speed CHECK (
    speed_kmh IS NULL OR (isfinite(speed_kmh) AND speed_kmh BETWEEN 0 AND 250)
  ),
  CONSTRAINT ck_fgp_accuracy CHECK (
    accuracy_m IS NULL OR (isfinite(accuracy_m) AND accuracy_m BETWEEN 0 AND 10000)
  )
);
CREATE INDEX ix_fgp_latest
  ON fleet_gps_position (tenant_id, vehicle_id, recorded_at DESC);
CREATE INDEX ix_fgp_site_time
  ON fleet_gps_position (tenant_id, site_id, recorded_at DESC);
SELECT app.apply_tenant_rls('fleet_gps_position', 'SELECT, INSERT');
CREATE TRIGGER tg_fleet_gps_position_append_only
  BEFORE UPDATE OR DELETE ON fleet_gps_position
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
"""

DOWNGRADE = r"""
DROP TABLE fleet_gps_position;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
