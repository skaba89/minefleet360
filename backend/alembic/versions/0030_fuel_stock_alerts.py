"""Alertes persistantes de seuil bas pour les cuves carburant.

Revision ID: 0030
Revises: 0029
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE fuel_stock_alert (
  fuel_stock_alert_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  fuel_tank_id uuid NOT NULL,
  threshold_liters numeric(12,3) NOT NULL,
  balance_liters numeric(12,3) NOT NULL,
  triggered_at timestamptz NOT NULL DEFAULT now(),
  acknowledged_by uuid,
  acknowledged_at timestamptz,
  resolved_at timestamptz,
  resolution_balance_liters numeric(12,3),
  CONSTRAINT uq_fuel_stock_alert_tenant UNIQUE (tenant_id, fuel_stock_alert_id),
  CONSTRAINT fk_fuel_stock_alert_tank FOREIGN KEY (tenant_id, fuel_tank_id, site_id)
    REFERENCES fuel_tank (tenant_id, fuel_tank_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fuel_stock_alert_ack_user FOREIGN KEY (tenant_id, acknowledged_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_fuel_stock_alert_values CHECK (
    threshold_liters > 0 AND balance_liters >= 0 AND
    (resolution_balance_liters IS NULL OR resolution_balance_liters >= 0)
  ),
  CONSTRAINT ck_fuel_stock_alert_ack CHECK (
    (acknowledged_by IS NULL AND acknowledged_at IS NULL) OR
    (acknowledged_by IS NOT NULL AND acknowledged_at IS NOT NULL)
  ),
  CONSTRAINT ck_fuel_stock_alert_resolution CHECK (
    (resolved_at IS NULL AND resolution_balance_liters IS NULL) OR
    (resolved_at IS NOT NULL AND resolution_balance_liters IS NOT NULL)
  )
);
CREATE UNIQUE INDEX uq_fuel_stock_alert_active ON fuel_stock_alert (tenant_id, fuel_tank_id)
  WHERE resolved_at IS NULL;
CREATE INDEX ix_fuel_stock_alert_site_time
  ON fuel_stock_alert (tenant_id, site_id, triggered_at DESC);
SELECT app.apply_tenant_rls('fuel_stock_alert', 'SELECT, INSERT, UPDATE');

INSERT INTO fuel_stock_alert (
  tenant_id, site_id, fuel_tank_id, threshold_liters, balance_liters
)
SELECT
  tank.tenant_id,
  tank.site_id,
  tank.fuel_tank_id,
  tank.low_stock_threshold_liters,
  COALESCE(SUM(
    CASE
      WHEN movement.movement_type IN ('RECEIPT', 'STOCKTAKE_IN') THEN movement.liters
      WHEN movement.fuel_stock_movement_id IS NOT NULL THEN -movement.liters
      ELSE 0
    END
  ), 0)::numeric(12,3)
FROM fuel_tank AS tank
LEFT JOIN fuel_stock_movement AS movement
  ON movement.tenant_id = tank.tenant_id
  AND movement.fuel_tank_id = tank.fuel_tank_id
WHERE tank.low_stock_threshold_liters IS NOT NULL
GROUP BY tank.tenant_id, tank.site_id, tank.fuel_tank_id, tank.low_stock_threshold_liters
HAVING COALESCE(SUM(
  CASE
    WHEN movement.movement_type IN ('RECEIPT', 'STOCKTAKE_IN') THEN movement.liters
    WHEN movement.fuel_stock_movement_id IS NOT NULL THEN -movement.liters
    ELSE 0
  END
), 0) <= tank.low_stock_threshold_liters;
"""

DOWNGRADE = r"""
DROP TABLE fuel_stock_alert;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
