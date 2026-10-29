"""Cuves, journal de stock append-only et approbation des ravitaillements.

Revision ID: 0027
Revises: 0026
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE vehicle ADD CONSTRAINT uq_vehicle_tenant_vehicle_site
  UNIQUE (tenant_id, vehicle_id, site_id);
ALTER TABLE driver ADD CONSTRAINT uq_driver_tenant_driver_site
  UNIQUE (tenant_id, driver_id, site_id);

CREATE TABLE fuel_tank (
  fuel_tank_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  code text NOT NULL,
  fuel_type text NOT NULL,
  capacity_liters numeric(12,3) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid,
  updated_by uuid,
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT uq_fuel_tank_tenant_id UNIQUE (tenant_id, fuel_tank_id),
  CONSTRAINT uq_fuel_tank_site_id UNIQUE (tenant_id, fuel_tank_id, site_id),
  CONSTRAINT fk_fuel_tank_site FOREIGN KEY (tenant_id, site_id)
    REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT ck_fuel_tank_code CHECK (code ~ '^[A-Za-z0-9_-]{1,32}$'),
  CONSTRAINT ck_fuel_tank_type CHECK (fuel_type IN ('DIESEL','PETROL')),
  CONSTRAINT ck_fuel_tank_capacity CHECK (capacity_liters > 0 AND capacity_liters <= 2000000)
);
CREATE UNIQUE INDEX uq_fuel_tank_site_code ON fuel_tank (tenant_id, site_id, lower(code));
SELECT app.apply_tenant_rls('fuel_tank', 'SELECT, INSERT, UPDATE');
CREATE TRIGGER tg_fuel_tank_touch BEFORE UPDATE ON fuel_tank
  FOR EACH ROW EXECUTE FUNCTION app.tg_touch();

CREATE TABLE fuel_issue (
  fuel_issue_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  fuel_tank_id uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  driver_id uuid NOT NULL,
  liters numeric(12,3) NOT NULL,
  meter_kind text,
  meter_value numeric(12,1),
  requested_at timestamptz NOT NULL,
  requested_by uuid NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_fuel_issue_tenant_id UNIQUE (tenant_id, fuel_issue_id),
  CONSTRAINT fk_fuel_issue_tank FOREIGN KEY (tenant_id, fuel_tank_id, site_id)
    REFERENCES fuel_tank (tenant_id, fuel_tank_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fuel_issue_vehicle FOREIGN KEY (tenant_id, vehicle_id, site_id)
    REFERENCES vehicle (tenant_id, vehicle_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fuel_issue_driver FOREIGN KEY (tenant_id, driver_id, site_id)
    REFERENCES driver (tenant_id, driver_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fuel_issue_requester FOREIGN KEY (tenant_id, requested_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_fuel_issue_liters CHECK (liters > 0 AND liters <= 100000),
  CONSTRAINT ck_fuel_issue_meter CHECK (
    (meter_kind IS NULL AND meter_value IS NULL) OR
    (meter_kind IN ('ODOMETER','HOUR_METER') AND meter_value IS NOT NULL AND meter_value >= 0)
  )
);
CREATE INDEX ix_fuel_issue_site_time ON fuel_issue (tenant_id, site_id, requested_at DESC);
CREATE INDEX ix_fuel_issue_tank_time ON fuel_issue (tenant_id, fuel_tank_id, requested_at);
SELECT app.apply_tenant_rls('fuel_issue', 'SELECT, INSERT');
CREATE TRIGGER tg_fuel_issue_append_only BEFORE UPDATE OR DELETE ON fuel_issue
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();

CREATE TABLE fuel_issue_decision (
  fuel_issue_decision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  fuel_issue_id uuid NOT NULL,
  decision text NOT NULL,
  reason_code text,
  decided_by uuid NOT NULL,
  decided_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_fuel_issue_decision_tenant_id UNIQUE (tenant_id, fuel_issue_decision_id),
  CONSTRAINT uq_fuel_issue_one_decision UNIQUE (tenant_id, fuel_issue_id),
  CONSTRAINT fk_fuel_issue_decision_issue FOREIGN KEY (tenant_id, fuel_issue_id)
    REFERENCES fuel_issue (tenant_id, fuel_issue_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fuel_issue_decision_user FOREIGN KEY (tenant_id, decided_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_fuel_issue_decision CHECK (decision IN ('APPROVED','REJECTED')),
  CONSTRAINT ck_fuel_issue_decision_reason CHECK (
    (decision = 'APPROVED' AND reason_code IS NULL) OR
    (decision = 'REJECTED' AND reason_code IS NOT NULL AND reason_code IN ('WRONG_VEHICLE','INVALID_QUANTITY','OTHER'))
  )
);
SELECT app.apply_tenant_rls('fuel_issue_decision', 'SELECT, INSERT');
CREATE TRIGGER tg_fuel_issue_decision_append_only BEFORE UPDATE OR DELETE ON fuel_issue_decision
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();

CREATE TABLE fuel_stock_movement (
  fuel_stock_movement_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  fuel_tank_id uuid NOT NULL,
  movement_type text NOT NULL,
  liters numeric(12,3) NOT NULL,
  reference text,
  fuel_issue_id uuid,
  occurred_at timestamptz NOT NULL,
  recorded_by uuid NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_fuel_movement_tenant_id UNIQUE (tenant_id, fuel_stock_movement_id),
  CONSTRAINT fk_fuel_movement_tank FOREIGN KEY (tenant_id, fuel_tank_id, site_id)
    REFERENCES fuel_tank (tenant_id, fuel_tank_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fuel_movement_issue FOREIGN KEY (tenant_id, fuel_issue_id)
    REFERENCES fuel_issue (tenant_id, fuel_issue_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fuel_movement_user FOREIGN KEY (tenant_id, recorded_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_fuel_movement_liters CHECK (liters > 0),
  CONSTRAINT ck_fuel_movement_type CHECK (movement_type IN ('RECEIPT','ISSUE')),
  CONSTRAINT ck_fuel_movement_source CHECK (
    (movement_type = 'RECEIPT' AND reference IS NOT NULL AND fuel_issue_id IS NULL) OR
    (movement_type = 'ISSUE' AND reference IS NULL AND fuel_issue_id IS NOT NULL)
  )
);
CREATE UNIQUE INDEX uq_fuel_receipt_reference ON fuel_stock_movement
  (tenant_id, fuel_tank_id, lower(reference)) WHERE movement_type = 'RECEIPT';
CREATE UNIQUE INDEX uq_fuel_issue_movement ON fuel_stock_movement (tenant_id, fuel_issue_id)
  WHERE fuel_issue_id IS NOT NULL;
CREATE INDEX ix_fuel_movement_tank_time ON fuel_stock_movement (tenant_id, fuel_tank_id, occurred_at DESC);
SELECT app.apply_tenant_rls('fuel_stock_movement', 'SELECT, INSERT');
CREATE TRIGGER tg_fuel_stock_movement_append_only BEFORE UPDATE OR DELETE ON fuel_stock_movement
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
"""

DOWNGRADE = r"""
DROP TABLE fuel_stock_movement;
DROP TABLE fuel_issue_decision;
DROP TABLE fuel_issue;
DROP TABLE fuel_tank;
ALTER TABLE driver DROP CONSTRAINT uq_driver_tenant_driver_site;
ALTER TABLE vehicle DROP CONSTRAINT uq_vehicle_tenant_vehicle_site;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
