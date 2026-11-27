"""Persist qualified clearance dimensions; unknown remains unavailable.

Revision ID: 0086
Revises: 0085
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE mining_road_restriction
  ADD COLUMN max_height_mm integer CHECK (max_height_mm > 0),
  ADD COLUMN max_width_mm integer CHECK (max_width_mm > 0),
  ADD COLUMN max_length_mm integer CHECK (max_length_mm > 0),
  ADD CONSTRAINT ck_mining_road_dimensions_complete CHECK (
    (max_height_mm IS NULL AND max_width_mm IS NULL AND max_length_mm IS NULL)
    OR
    (max_height_mm IS NOT NULL AND max_width_mm IS NOT NULL AND max_length_mm IS NOT NULL)
  );
COMMENT ON COLUMN mining_road_restriction.max_height_mm IS
  'Qualified maximum vehicle height in mm; NULL means unknown, never unlimited';
COMMENT ON COLUMN mining_road_restriction.max_width_mm IS
  'Qualified maximum vehicle width in mm; NULL means unknown, never unlimited';
COMMENT ON COLUMN mining_road_restriction.max_length_mm IS
  'Qualified maximum vehicle length in mm; NULL means unknown, never unlimited';
"""

DOWNGRADE = r"""
ALTER TABLE mining_road_restriction
  DROP CONSTRAINT ck_mining_road_dimensions_complete,
  DROP COLUMN max_length_mm,
  DROP COLUMN max_width_mm,
  DROP COLUMN max_height_mm;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
