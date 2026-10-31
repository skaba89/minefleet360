"""Purchase order drafts tied to approved spare-part replenishments.

Revision ID: 0045
Revises: 0044
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE spare_part_replenishment
  ADD CONSTRAINT uq_replenishment_tenant_id UNIQUE (tenant_id, replenishment_id);

CREATE TABLE spare_part_purchase_order (
  purchase_order_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  replenishment_id uuid NOT NULL,
  supplier_name text NOT NULL,
  supplier_reference text NOT NULL,
  quantity numeric(16,3) NOT NULL,
  status text NOT NULL DEFAULT 'DRAFT',
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_purchase_replenishment FOREIGN KEY (tenant_id, replenishment_id)
    REFERENCES spare_part_replenishment (tenant_id, replenishment_id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_site FOREIGN KEY (tenant_id, site_id)
    REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT uq_purchase_replenishment UNIQUE (tenant_id, replenishment_id),
  CONSTRAINT ck_purchase_qty_positive CHECK (quantity > 0),
  CONSTRAINT ck_purchase_supplier CHECK (char_length(trim(supplier_name)) BETWEEN 1 AND 200),
  CONSTRAINT ck_purchase_reference CHECK (char_length(trim(supplier_reference)) BETWEEN 1 AND 120),
  CONSTRAINT ck_purchase_status CHECK (status = 'DRAFT')
);
CREATE INDEX ix_purchase_site ON spare_part_purchase_order (tenant_id, site_id);
SELECT app.apply_tenant_rls('spare_part_purchase_order', 'SELECT, INSERT');
"""

DOWNGRADE = r"""
DROP TABLE spare_part_purchase_order;
ALTER TABLE spare_part_replenishment DROP CONSTRAINT uq_replenishment_tenant_id;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
