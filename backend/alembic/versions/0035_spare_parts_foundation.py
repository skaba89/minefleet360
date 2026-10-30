"""Fondation de catalogue des pièces, magasins et états de stock.

Revision ID: 0035
Revises: 0034
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE spare_part (
  spare_part_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  code text NOT NULL,
  name text NOT NULL,
  unit text NOT NULL DEFAULT 'EACH',
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_spare_part_tenant_id UNIQUE (tenant_id, spare_part_id),
  CONSTRAINT fk_spare_part_tenant FOREIGN KEY (tenant_id)
    REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT ck_spare_part_code CHECK (code ~ '^[A-Za-z0-9_-]{1,48}$'),
  CONSTRAINT ck_spare_part_name CHECK (char_length(trim(name)) BETWEEN 1 AND 200),
  CONSTRAINT ck_spare_part_unit CHECK (unit IN ('EACH', 'LITER', 'KG', 'METER'))
);
CREATE UNIQUE INDEX uq_spare_part_tenant_code ON spare_part (tenant_id, lower(code));
SELECT app.apply_tenant_rls('spare_part', 'SELECT, INSERT, UPDATE');

CREATE TABLE spare_part_store (
  spare_part_store_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  code text NOT NULL,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_spare_part_store_tenant_id UNIQUE (tenant_id, spare_part_store_id),
  CONSTRAINT uq_spare_part_store_site_id UNIQUE (tenant_id, spare_part_store_id, site_id),
  CONSTRAINT fk_spare_part_store_site FOREIGN KEY (tenant_id, site_id)
    REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT ck_spare_part_store_code CHECK (code ~ '^[A-Za-z0-9_-]{1,48}$'),
  CONSTRAINT ck_spare_part_store_name CHECK (char_length(trim(name)) BETWEEN 1 AND 200)
);
CREATE UNIQUE INDEX uq_spare_part_store_site_code
  ON spare_part_store (tenant_id, site_id, lower(code));
SELECT app.apply_tenant_rls('spare_part_store', 'SELECT, INSERT, UPDATE');

CREATE TABLE spare_part_balance (
  spare_part_balance_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  spare_part_store_id uuid NOT NULL,
  spare_part_id uuid NOT NULL,
  on_hand numeric(16,3) NOT NULL DEFAULT 0,
  reserved numeric(16,3) NOT NULL DEFAULT 0,
  low_stock_threshold numeric(16,3) NOT NULL DEFAULT 0,
  CONSTRAINT uq_spare_part_balance_tenant_id UNIQUE (tenant_id, spare_part_balance_id),
  CONSTRAINT uq_spare_part_balance_store_part
    UNIQUE (tenant_id, spare_part_store_id, spare_part_id),
  CONSTRAINT fk_spare_part_balance_store FOREIGN KEY (tenant_id, spare_part_store_id, site_id)
    REFERENCES spare_part_store (tenant_id, spare_part_store_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_spare_part_balance_part FOREIGN KEY (tenant_id, spare_part_id)
    REFERENCES spare_part (tenant_id, spare_part_id) ON DELETE RESTRICT,
  CONSTRAINT ck_spare_part_balance_nonnegative CHECK (
    on_hand >= 0 AND reserved >= 0 AND reserved <= on_hand AND low_stock_threshold >= 0
  )
);
CREATE INDEX ix_spare_part_balance_site ON spare_part_balance (tenant_id, site_id);
SELECT app.apply_tenant_rls('spare_part_balance', 'SELECT, INSERT, UPDATE');
"""

DOWNGRADE = r"""
DROP TABLE spare_part_balance;
DROP TABLE spare_part_store;
DROP TABLE spare_part;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
