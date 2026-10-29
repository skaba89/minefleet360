"""Inventaires physiques, corrections du journal et seuils de stock carburant.

Revision ID: 0028
Revises: 0027
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE fuel_tank ADD COLUMN low_stock_threshold_liters numeric(12,3);
ALTER TABLE fuel_tank ADD CONSTRAINT ck_fuel_tank_threshold CHECK (
  low_stock_threshold_liters IS NULL OR
  (low_stock_threshold_liters > 0 AND low_stock_threshold_liters <= capacity_liters)
);

CREATE TABLE fuel_stocktake (
  fuel_stocktake_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  fuel_tank_id uuid NOT NULL,
  expected_liters numeric(12,3) NOT NULL,
  counted_liters numeric(12,3) NOT NULL,
  delta_liters numeric(12,3) NOT NULL,
  reference text NOT NULL,
  reason_code text NOT NULL,
  occurred_at timestamptz NOT NULL,
  recorded_by uuid NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_fuel_stocktake_tenant UNIQUE (tenant_id, fuel_stocktake_id),
  CONSTRAINT uq_fuel_stocktake_tank_site UNIQUE (tenant_id, fuel_stocktake_id, fuel_tank_id, site_id),
  CONSTRAINT fk_fuel_stocktake_tank FOREIGN KEY (tenant_id, fuel_tank_id, site_id)
    REFERENCES fuel_tank (tenant_id, fuel_tank_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fuel_stocktake_user FOREIGN KEY (tenant_id, recorded_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_fuel_stocktake_expected CHECK (expected_liters >= 0),
  CONSTRAINT ck_fuel_stocktake_counted CHECK (counted_liters >= 0),
  CONSTRAINT ck_fuel_stocktake_delta CHECK (delta_liters = counted_liters - expected_liters),
  CONSTRAINT ck_fuel_stocktake_reference CHECK (reference ~ '^[A-Za-z0-9/_ .-]{1,60}$'),
  CONSTRAINT ck_fuel_stocktake_reason CHECK (
    reason_code IN ('MEASUREMENT','LOSS','DATA_CORRECTION','OTHER')
  )
);
CREATE UNIQUE INDEX uq_fuel_stocktake_reference ON fuel_stocktake
  (tenant_id, fuel_tank_id, lower(reference));
CREATE INDEX ix_fuel_stocktake_site_time ON fuel_stocktake (tenant_id, site_id, occurred_at DESC);
SELECT app.apply_tenant_rls('fuel_stocktake', 'SELECT, INSERT');
CREATE TRIGGER tg_fuel_stocktake_append_only BEFORE UPDATE OR DELETE ON fuel_stocktake
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();

ALTER TABLE fuel_stock_movement ADD COLUMN fuel_stocktake_id uuid;
ALTER TABLE fuel_stock_movement DROP CONSTRAINT ck_fuel_movement_type;
ALTER TABLE fuel_stock_movement ADD CONSTRAINT ck_fuel_movement_type CHECK (
  movement_type IN ('RECEIPT','ISSUE','STOCKTAKE_IN','STOCKTAKE_OUT')
);
ALTER TABLE fuel_stock_movement DROP CONSTRAINT ck_fuel_movement_source;
ALTER TABLE fuel_stock_movement ADD CONSTRAINT ck_fuel_movement_source CHECK (
  (movement_type = 'RECEIPT' AND reference IS NOT NULL AND fuel_issue_id IS NULL AND fuel_stocktake_id IS NULL) OR
  (movement_type = 'ISSUE' AND reference IS NULL AND fuel_issue_id IS NOT NULL AND fuel_stocktake_id IS NULL) OR
  (movement_type IN ('STOCKTAKE_IN','STOCKTAKE_OUT') AND reference IS NULL AND
    fuel_issue_id IS NULL AND fuel_stocktake_id IS NOT NULL)
);
ALTER TABLE fuel_stock_movement ADD CONSTRAINT fk_fuel_movement_stocktake
  FOREIGN KEY (tenant_id, fuel_stocktake_id, fuel_tank_id, site_id)
  REFERENCES fuel_stocktake (tenant_id, fuel_stocktake_id, fuel_tank_id, site_id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX uq_fuel_stocktake_movement ON fuel_stock_movement (tenant_id, fuel_stocktake_id)
  WHERE fuel_stocktake_id IS NOT NULL;
"""

DOWNGRADE = r"""
DROP TRIGGER tg_fuel_stock_movement_append_only ON fuel_stock_movement;
DELETE FROM fuel_stock_movement WHERE fuel_stocktake_id IS NOT NULL;
ALTER TABLE fuel_stock_movement DROP CONSTRAINT fk_fuel_movement_stocktake;
DROP INDEX uq_fuel_stocktake_movement;
ALTER TABLE fuel_stock_movement DROP CONSTRAINT ck_fuel_movement_source;
ALTER TABLE fuel_stock_movement ADD CONSTRAINT ck_fuel_movement_source CHECK (
  (movement_type = 'RECEIPT' AND reference IS NOT NULL AND fuel_issue_id IS NULL) OR
  (movement_type = 'ISSUE' AND reference IS NULL AND fuel_issue_id IS NOT NULL)
);
ALTER TABLE fuel_stock_movement DROP CONSTRAINT ck_fuel_movement_type;
ALTER TABLE fuel_stock_movement ADD CONSTRAINT ck_fuel_movement_type CHECK (movement_type IN ('RECEIPT','ISSUE'));
ALTER TABLE fuel_stock_movement DROP COLUMN fuel_stocktake_id;
CREATE TRIGGER tg_fuel_stock_movement_append_only BEFORE UPDATE OR DELETE ON fuel_stock_movement
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
DROP TABLE fuel_stocktake;
ALTER TABLE fuel_tank DROP CONSTRAINT ck_fuel_tank_threshold;
ALTER TABLE fuel_tank DROP COLUMN low_stock_threshold_liters;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
