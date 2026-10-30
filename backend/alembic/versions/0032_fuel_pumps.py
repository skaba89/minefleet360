"""Pompes carburant et relevés cumulés append-only.

Revision ID: 0032
Revises: 0031
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE fuel_pump (
  fuel_pump_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  fuel_tank_id uuid NOT NULL,
  code text NOT NULL,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid,
  updated_by uuid,
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT uq_fuel_pump_tenant UNIQUE (tenant_id, fuel_pump_id),
  CONSTRAINT uq_fuel_pump_site UNIQUE (tenant_id, fuel_pump_id, site_id),
  CONSTRAINT fk_fuel_pump_tank FOREIGN KEY (tenant_id, fuel_tank_id, site_id)
    REFERENCES fuel_tank (tenant_id, fuel_tank_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT ck_fuel_pump_code CHECK (code ~ '^[A-Za-z0-9_-]{1,32}$'),
  CONSTRAINT ck_fuel_pump_name CHECK (char_length(name) BETWEEN 2 AND 120)
);
CREATE UNIQUE INDEX uq_fuel_pump_site_code
  ON fuel_pump (tenant_id, site_id, lower(code));
CREATE INDEX ix_fuel_pump_tank ON fuel_pump (tenant_id, fuel_tank_id);
SELECT app.apply_tenant_rls('fuel_pump', 'SELECT, INSERT, UPDATE');
CREATE TRIGGER tg_fuel_pump_touch BEFORE UPDATE ON fuel_pump
  FOR EACH ROW EXECUTE FUNCTION app.tg_touch();

CREATE TABLE fuel_pump_meter_reading (
  fuel_pump_meter_reading_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  fuel_pump_id uuid NOT NULL,
  cumulative_liters numeric(16,3) NOT NULL,
  measured_at timestamptz NOT NULL,
  source text NOT NULL,
  source_reference text NOT NULL,
  recorded_by uuid NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_fuel_pump_reading_tenant UNIQUE (
    tenant_id, fuel_pump_meter_reading_id
  ),
  CONSTRAINT fk_fuel_pump_reading_pump FOREIGN KEY (tenant_id, fuel_pump_id, site_id)
    REFERENCES fuel_pump (tenant_id, fuel_pump_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fuel_pump_reading_user FOREIGN KEY (tenant_id, recorded_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_fuel_pump_reading_value CHECK (
    cumulative_liters >= 0 AND cumulative_liters <= 9999999999999
  ),
  CONSTRAINT ck_fuel_pump_reading_source CHECK (source IN ('MANUAL','DEVICE')),
  CONSTRAINT ck_fuel_pump_reading_reference CHECK (
    source_reference ~ '^[A-Za-z0-9/_ .:-]{1,80}$'
  )
);
CREATE UNIQUE INDEX uq_fuel_pump_reading_source
  ON fuel_pump_meter_reading (tenant_id, fuel_pump_id, lower(source_reference));
CREATE INDEX ix_fuel_pump_reading_time
  ON fuel_pump_meter_reading (tenant_id, fuel_pump_id, measured_at DESC);
SELECT app.apply_tenant_rls('fuel_pump_meter_reading', 'SELECT, INSERT');
CREATE TRIGGER tg_fuel_pump_meter_reading_append_only
  BEFORE UPDATE OR DELETE ON fuel_pump_meter_reading
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
"""

DOWNGRADE = r"""
DROP TABLE fuel_pump_meter_reading;
DROP TABLE fuel_pump;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
