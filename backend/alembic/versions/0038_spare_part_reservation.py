"""Fondation des réservations de pièces liées à un ordre de travail.

Revision ID: 0038
Revises: 0037
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

UPGRADE = r"""
-- La clé composite impose que l'OT et le magasin appartiennent au même site.
ALTER TABLE work_order
  ADD CONSTRAINT uq_work_order_tenant_id_site
  UNIQUE (tenant_id, work_order_id, site_id);

CREATE TABLE spare_part_reservation (
  spare_part_reservation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  work_order_id uuid NOT NULL,
  spare_part_store_id uuid NOT NULL,
  spare_part_id uuid NOT NULL,
  quantity numeric(16,3) NOT NULL,
  status text NOT NULL DEFAULT 'ACTIVE',
  reference text NOT NULL,
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  released_at timestamptz,
  CONSTRAINT uq_spare_part_reservation_tenant_id
    UNIQUE (tenant_id, spare_part_reservation_id),
  CONSTRAINT uq_spare_part_reservation_reference
    UNIQUE (tenant_id, spare_part_store_id, reference),
  CONSTRAINT fk_spare_part_reservation_work_order
    FOREIGN KEY (tenant_id, work_order_id, site_id)
    REFERENCES work_order (tenant_id, work_order_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_spare_part_reservation_store
    FOREIGN KEY (tenant_id, spare_part_store_id, site_id)
    REFERENCES spare_part_store (tenant_id, spare_part_store_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_spare_part_reservation_part
    FOREIGN KEY (tenant_id, spare_part_id)
    REFERENCES spare_part (tenant_id, spare_part_id) ON DELETE RESTRICT,
  CONSTRAINT fk_spare_part_reservation_user
    FOREIGN KEY (tenant_id, created_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_spare_part_reservation_quantity CHECK (quantity > 0),
  CONSTRAINT ck_spare_part_reservation_status CHECK (status IN ('ACTIVE', 'CONSUMED', 'RELEASED')),
  CONSTRAINT ck_spare_part_reservation_reference CHECK (
    char_length(trim(reference)) BETWEEN 1 AND 120
  ),
  CONSTRAINT ck_spare_part_reservation_released CHECK (
    (status = 'ACTIVE' AND released_at IS NULL)
    OR (status <> 'ACTIVE' AND released_at IS NOT NULL)
  )
);
CREATE INDEX ix_spare_part_reservation_work_order
  ON spare_part_reservation (tenant_id, work_order_id, status);
CREATE INDEX ix_spare_part_reservation_store
  ON spare_part_reservation (tenant_id, spare_part_store_id, spare_part_id, status);
SELECT app.apply_tenant_rls('spare_part_reservation', 'SELECT, INSERT, UPDATE');
"""

DOWNGRADE = r"""
DROP TABLE spare_part_reservation;
ALTER TABLE work_order DROP CONSTRAINT uq_work_order_tenant_id_site;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
