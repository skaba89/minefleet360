"""Persisted spare-parts replenishment drafts, scoped by tenant and store.

Revision ID: 0042
Revises: 0041
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE spare_part_replenishment (
  replenishment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  spare_part_store_id uuid NOT NULL,
  spare_part_id uuid NOT NULL,
  quantity numeric(16,3) NOT NULL,
  reference text NOT NULL,
  status text NOT NULL DEFAULT 'DRAFT',
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_replenishment_store
    FOREIGN KEY (tenant_id, spare_part_store_id, site_id)
    REFERENCES spare_part_store (tenant_id, spare_part_store_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_replenishment_part
    FOREIGN KEY (tenant_id, spare_part_id)
    REFERENCES spare_part (tenant_id, spare_part_id) ON DELETE RESTRICT,
  CONSTRAINT ck_replenishment_quantity CHECK (quantity > 0),
  CONSTRAINT ck_replenishment_reference CHECK (char_length(trim(reference)) BETWEEN 1 AND 120),
  CONSTRAINT ck_replenishment_status CHECK (status IN ('DRAFT')),
  CONSTRAINT uq_replenishment_reference UNIQUE (tenant_id, reference)
);
CREATE INDEX ix_replenishment_site ON spare_part_replenishment (tenant_id, site_id);
SELECT app.apply_tenant_rls('spare_part_replenishment', 'SELECT, INSERT');
"""

DOWNGRADE = r"""
DROP TABLE spare_part_replenishment;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
