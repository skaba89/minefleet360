"""Traçabilité explicite de la consommation des pièces par ordre de travail.

Revision ID: 0041
Revises: 0040
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE spare_part_movement
  ADD COLUMN work_order_id uuid,
  ADD COLUMN spare_part_reservation_id uuid,
  ADD CONSTRAINT fk_part_movement_work_order
    FOREIGN KEY (tenant_id, work_order_id, site_id)
    REFERENCES work_order (tenant_id, work_order_id, site_id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_part_movement_reservation
    FOREIGN KEY (tenant_id, spare_part_reservation_id)
    REFERENCES spare_part_reservation (tenant_id, spare_part_reservation_id) ON DELETE RESTRICT,
  ADD CONSTRAINT ck_part_movement_ot_issue_only CHECK (
    (work_order_id IS NULL AND spare_part_reservation_id IS NULL)
    OR (movement_type = 'ISSUE' AND work_order_id IS NOT NULL
        AND spare_part_reservation_id IS NOT NULL)
  );
CREATE UNIQUE INDEX uq_part_movement_reservation_consumption
  ON spare_part_movement (tenant_id, spare_part_reservation_id)
  WHERE spare_part_reservation_id IS NOT NULL;
CREATE INDEX ix_part_movement_work_order
  ON spare_part_movement (tenant_id, work_order_id)
  WHERE work_order_id IS NOT NULL;
COMMENT ON COLUMN spare_part_movement.work_order_id IS
  'Explicit OT link for reservation consumption; historical movements remain NULL.';
"""

DOWNGRADE = r"""
DROP INDEX ix_part_movement_work_order;
DROP INDEX uq_part_movement_reservation_consumption;
ALTER TABLE spare_part_movement
  DROP CONSTRAINT ck_part_movement_ot_issue_only,
  DROP CONSTRAINT fk_part_movement_reservation,
  DROP CONSTRAINT fk_part_movement_work_order,
  DROP COLUMN spare_part_reservation_id,
  DROP COLUMN work_order_id;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
