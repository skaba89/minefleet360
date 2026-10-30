"""Journal immuable des mouvements de pièces.

Revision ID: 0037
Revises: 0036
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE spare_part_movement (
  spare_part_movement_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  spare_part_store_id uuid NOT NULL,
  spare_part_id uuid NOT NULL,
  movement_type text NOT NULL,
  quantity numeric(16,3) NOT NULL,
  reference text NOT NULL,
  recorded_by uuid NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_spare_part_movement_tenant_id UNIQUE (tenant_id, spare_part_movement_id),
  CONSTRAINT uq_spare_part_movement_reference
    UNIQUE (tenant_id, spare_part_store_id, reference),
  CONSTRAINT fk_spare_part_movement_store FOREIGN KEY (tenant_id, spare_part_store_id, site_id)
    REFERENCES spare_part_store (tenant_id, spare_part_store_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_spare_part_movement_part FOREIGN KEY (tenant_id, spare_part_id)
    REFERENCES spare_part (tenant_id, spare_part_id) ON DELETE RESTRICT,
  CONSTRAINT fk_spare_part_movement_user FOREIGN KEY (tenant_id, recorded_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_spare_part_movement_type CHECK (
    movement_type IN ('RECEIPT', 'ISSUE', 'ADJUSTMENT_IN', 'ADJUSTMENT_OUT')
  ),
  CONSTRAINT ck_spare_part_movement_quantity CHECK (quantity > 0),
  CONSTRAINT ck_spare_part_movement_reference CHECK (char_length(trim(reference)) BETWEEN 1 AND 120)
);
CREATE INDEX ix_spare_part_movement_site_time
  ON spare_part_movement (tenant_id, site_id, recorded_at DESC);
CREATE INDEX ix_spare_part_movement_part_time
  ON spare_part_movement (tenant_id, spare_part_id, recorded_at DESC);
SELECT app.apply_tenant_rls('spare_part_movement', 'SELECT, INSERT');
CREATE TRIGGER tg_spare_part_movement_append_only
  BEFORE UPDATE OR DELETE ON spare_part_movement
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
"""

DOWNGRADE = r"""
DROP TABLE spare_part_movement;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
