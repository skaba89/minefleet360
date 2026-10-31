"""Permit submitting replenishment drafts after review.

Revision ID: 0043
Revises: 0042
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE spare_part_replenishment
  DROP CONSTRAINT ck_replenishment_status,
  ADD CONSTRAINT ck_replenishment_status CHECK (status IN ('DRAFT', 'SUBMITTED')),
  ADD COLUMN submitted_at timestamptz;
"""
DOWNGRADE = r"""
UPDATE spare_part_replenishment SET status = 'DRAFT', submitted_at = NULL
  WHERE status = 'SUBMITTED';
ALTER TABLE spare_part_replenishment
  DROP COLUMN submitted_at,
  DROP CONSTRAINT ck_replenishment_status,
  ADD CONSTRAINT ck_replenishment_status CHECK (status IN ('DRAFT'));
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
