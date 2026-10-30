"""Fournisseurs, commandes approuvées et réceptions de carburant.

Revision ID: 0031
Revises: 0030
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE fuel_supplier (
  fuel_supplier_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  code text NOT NULL,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid,
  updated_by uuid,
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT uq_fuel_supplier_tenant UNIQUE (tenant_id, fuel_supplier_id),
  CONSTRAINT uq_fuel_supplier_site UNIQUE (tenant_id, fuel_supplier_id, site_id),
  CONSTRAINT fk_fuel_supplier_site FOREIGN KEY (tenant_id, site_id)
    REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT ck_fuel_supplier_code CHECK (code ~ '^[A-Za-z0-9_-]{1,32}$'),
  CONSTRAINT ck_fuel_supplier_name CHECK (char_length(name) BETWEEN 2 AND 120)
);
CREATE UNIQUE INDEX uq_fuel_supplier_site_code
  ON fuel_supplier (tenant_id, site_id, lower(code));
SELECT app.apply_tenant_rls('fuel_supplier', 'SELECT, INSERT');

CREATE TABLE fuel_purchase_order (
  fuel_purchase_order_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  fuel_supplier_id uuid NOT NULL,
  fuel_tank_id uuid NOT NULL,
  reference text NOT NULL,
  quantity_liters numeric(12,3) NOT NULL,
  unit_price numeric(16,2) NOT NULL,
  currency text NOT NULL,
  ordered_at timestamptz NOT NULL,
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_fuel_purchase_tenant UNIQUE (tenant_id, fuel_purchase_order_id),
  CONSTRAINT uq_fuel_purchase_tank_site UNIQUE (
    tenant_id, fuel_purchase_order_id, fuel_tank_id, site_id
  ),
  CONSTRAINT fk_fuel_purchase_supplier FOREIGN KEY (tenant_id, fuel_supplier_id, site_id)
    REFERENCES fuel_supplier (tenant_id, fuel_supplier_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fuel_purchase_tank FOREIGN KEY (tenant_id, fuel_tank_id, site_id)
    REFERENCES fuel_tank (tenant_id, fuel_tank_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fuel_purchase_creator FOREIGN KEY (tenant_id, created_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_fuel_purchase_reference CHECK (reference ~ '^[A-Za-z0-9/_ .-]{1,60}$'),
  CONSTRAINT ck_fuel_purchase_quantity CHECK (quantity_liters > 0 AND quantity_liters <= 2000000),
  CONSTRAINT ck_fuel_purchase_price CHECK (unit_price > 0),
  CONSTRAINT ck_fuel_purchase_currency CHECK (currency IN ('GNF','USD','EUR'))
);
CREATE UNIQUE INDEX uq_fuel_purchase_reference
  ON fuel_purchase_order (tenant_id, lower(reference));
CREATE INDEX ix_fuel_purchase_site_time
  ON fuel_purchase_order (tenant_id, site_id, ordered_at DESC);
-- UPDATE est requis par SELECT ... FOR UPDATE ; le trigger append-only interdit
-- toujours toute modification effective de la commande.
SELECT app.apply_tenant_rls('fuel_purchase_order', 'SELECT, INSERT, UPDATE');
CREATE TRIGGER tg_fuel_purchase_order_append_only
  BEFORE UPDATE OR DELETE ON fuel_purchase_order
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();

CREATE TABLE fuel_purchase_decision (
  fuel_purchase_decision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  fuel_purchase_order_id uuid NOT NULL,
  decision text NOT NULL,
  reason_code text,
  decided_by uuid NOT NULL,
  decided_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_fuel_purchase_decision_tenant UNIQUE (tenant_id, fuel_purchase_decision_id),
  CONSTRAINT uq_fuel_purchase_one_decision UNIQUE (tenant_id, fuel_purchase_order_id),
  CONSTRAINT fk_fuel_purchase_decision_order FOREIGN KEY (tenant_id, fuel_purchase_order_id)
    REFERENCES fuel_purchase_order (tenant_id, fuel_purchase_order_id) ON DELETE RESTRICT,
  CONSTRAINT fk_fuel_purchase_decision_user FOREIGN KEY (tenant_id, decided_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_fuel_purchase_decision CHECK (decision IN ('APPROVED','REJECTED')),
  CONSTRAINT ck_fuel_purchase_decision_reason CHECK (
    (decision = 'APPROVED' AND reason_code IS NULL) OR
    (decision = 'REJECTED' AND reason_code IS NOT NULL
      AND reason_code IN ('BUDGET','SUPPLIER','QUANTITY','OTHER'))
  )
);
SELECT app.apply_tenant_rls('fuel_purchase_decision', 'SELECT, INSERT');
CREATE TRIGGER tg_fuel_purchase_decision_append_only
  BEFORE UPDATE OR DELETE ON fuel_purchase_decision
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();

CREATE TABLE fuel_purchase_receipt (
  fuel_purchase_receipt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  fuel_purchase_order_id uuid NOT NULL,
  fuel_tank_id uuid NOT NULL,
  liters numeric(12,3) NOT NULL,
  delivery_reference text NOT NULL,
  occurred_at timestamptz NOT NULL,
  recorded_by uuid NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_fuel_purchase_receipt_tenant UNIQUE (tenant_id, fuel_purchase_receipt_id),
  CONSTRAINT uq_fuel_purchase_receipt_source UNIQUE (
    tenant_id, fuel_purchase_receipt_id, fuel_tank_id, site_id
  ),
  CONSTRAINT fk_fuel_purchase_receipt_order FOREIGN KEY (
    tenant_id, fuel_purchase_order_id, fuel_tank_id, site_id
  ) REFERENCES fuel_purchase_order (
    tenant_id, fuel_purchase_order_id, fuel_tank_id, site_id
  ) ON DELETE RESTRICT,
  CONSTRAINT fk_fuel_purchase_receipt_user FOREIGN KEY (tenant_id, recorded_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_fuel_purchase_receipt_liters CHECK (liters > 0 AND liters <= 2000000),
  CONSTRAINT ck_fuel_purchase_delivery_reference CHECK (
    delivery_reference ~ '^[A-Za-z0-9/_ .-]{1,60}$'
  )
);
CREATE UNIQUE INDEX uq_fuel_purchase_delivery_reference
  ON fuel_purchase_receipt (tenant_id, lower(delivery_reference));
CREATE INDEX ix_fuel_purchase_receipt_order_time
  ON fuel_purchase_receipt (tenant_id, fuel_purchase_order_id, occurred_at);
SELECT app.apply_tenant_rls('fuel_purchase_receipt', 'SELECT, INSERT');
CREATE TRIGGER tg_fuel_purchase_receipt_append_only
  BEFORE UPDATE OR DELETE ON fuel_purchase_receipt
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();

ALTER TABLE fuel_stock_movement ADD COLUMN fuel_purchase_receipt_id uuid;
ALTER TABLE fuel_stock_movement DROP CONSTRAINT ck_fuel_movement_type;
ALTER TABLE fuel_stock_movement ADD CONSTRAINT ck_fuel_movement_type CHECK (
  movement_type IN ('RECEIPT','ISSUE','STOCKTAKE_IN','STOCKTAKE_OUT','PURCHASE_RECEIPT')
);
ALTER TABLE fuel_stock_movement DROP CONSTRAINT ck_fuel_movement_source;
ALTER TABLE fuel_stock_movement ADD CONSTRAINT ck_fuel_movement_source CHECK (
  (movement_type = 'RECEIPT' AND reference IS NOT NULL AND fuel_issue_id IS NULL AND
    fuel_stocktake_id IS NULL AND fuel_purchase_receipt_id IS NULL) OR
  (movement_type = 'ISSUE' AND reference IS NULL AND fuel_issue_id IS NOT NULL AND
    fuel_stocktake_id IS NULL AND fuel_purchase_receipt_id IS NULL) OR
  (movement_type IN ('STOCKTAKE_IN','STOCKTAKE_OUT') AND reference IS NULL AND
    fuel_issue_id IS NULL AND fuel_stocktake_id IS NOT NULL AND fuel_purchase_receipt_id IS NULL) OR
  (movement_type = 'PURCHASE_RECEIPT' AND reference IS NULL AND fuel_issue_id IS NULL AND
    fuel_stocktake_id IS NULL AND fuel_purchase_receipt_id IS NOT NULL)
);
ALTER TABLE fuel_stock_movement ADD CONSTRAINT fk_fuel_movement_purchase_receipt
  FOREIGN KEY (tenant_id, fuel_purchase_receipt_id, fuel_tank_id, site_id)
  REFERENCES fuel_purchase_receipt (
    tenant_id, fuel_purchase_receipt_id, fuel_tank_id, site_id
  ) ON DELETE RESTRICT;
CREATE UNIQUE INDEX uq_fuel_purchase_receipt_movement
  ON fuel_stock_movement (tenant_id, fuel_purchase_receipt_id)
  WHERE fuel_purchase_receipt_id IS NOT NULL;
"""

DOWNGRADE = r"""
DROP TRIGGER tg_fuel_stock_movement_append_only ON fuel_stock_movement;
DELETE FROM fuel_stock_movement WHERE fuel_purchase_receipt_id IS NOT NULL;
ALTER TABLE fuel_stock_movement DROP CONSTRAINT fk_fuel_movement_purchase_receipt;
DROP INDEX uq_fuel_purchase_receipt_movement;
ALTER TABLE fuel_stock_movement DROP CONSTRAINT ck_fuel_movement_source;
ALTER TABLE fuel_stock_movement ADD CONSTRAINT ck_fuel_movement_source CHECK (
  (movement_type = 'RECEIPT' AND reference IS NOT NULL AND fuel_issue_id IS NULL AND fuel_stocktake_id IS NULL) OR
  (movement_type = 'ISSUE' AND reference IS NULL AND fuel_issue_id IS NOT NULL AND fuel_stocktake_id IS NULL) OR
  (movement_type IN ('STOCKTAKE_IN','STOCKTAKE_OUT') AND reference IS NULL AND
    fuel_issue_id IS NULL AND fuel_stocktake_id IS NOT NULL)
);
ALTER TABLE fuel_stock_movement DROP CONSTRAINT ck_fuel_movement_type;
ALTER TABLE fuel_stock_movement ADD CONSTRAINT ck_fuel_movement_type CHECK (
  movement_type IN ('RECEIPT','ISSUE','STOCKTAKE_IN','STOCKTAKE_OUT')
);
ALTER TABLE fuel_stock_movement DROP COLUMN fuel_purchase_receipt_id;
CREATE TRIGGER tg_fuel_stock_movement_append_only BEFORE UPDATE OR DELETE ON fuel_stock_movement
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
DROP TABLE fuel_purchase_receipt;
DROP TABLE fuel_purchase_decision;
DROP TABLE fuel_purchase_order;
DROP TABLE fuel_supplier;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
