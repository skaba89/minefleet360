"""Add review decisions to submitted replenishment requests.

Revision ID: 0044
Revises: 0043
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE spare_part_replenishment
  DROP CONSTRAINT ck_replenishment_status,
  ADD CONSTRAINT ck_replenishment_status
    CHECK (status IN ('DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED')),
  ADD COLUMN decision_by uuid,
  ADD COLUMN decided_at timestamptz,
  ADD COLUMN decision_note text,
  ADD CONSTRAINT ck_replenishment_decision_consistency CHECK (
    (status IN ('DRAFT', 'SUBMITTED') AND decision_by IS NULL AND decided_at IS NULL)
    OR (status IN ('APPROVED', 'REJECTED') AND decision_by IS NOT NULL AND decided_at IS NOT NULL)
  );
"""
DOWNGRADE = r"""
UPDATE spare_part_replenishment
SET status = 'SUBMITTED', decision_by = NULL, decided_at = NULL, decision_note = NULL
WHERE status IN ('APPROVED', 'REJECTED');
ALTER TABLE spare_part_replenishment
  DROP CONSTRAINT ck_replenishment_decision_consistency,
  DROP COLUMN decision_by,
  DROP COLUMN decided_at,
  DROP COLUMN decision_note,
  DROP CONSTRAINT ck_replenishment_status,
  ADD CONSTRAINT ck_replenishment_status CHECK (status IN ('DRAFT', 'SUBMITTED'));
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
