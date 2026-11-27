"""Store directional surveyed grades without inventing historical values.

Revision ID: 0087
Revises: 0086
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE mining_road_restriction
  ADD COLUMN uphill_permille integer CHECK (uphill_permille >= 0),
  ADD COLUMN downhill_permille integer CHECK (downhill_permille >= 0),
  ADD CONSTRAINT ck_mining_road_grades_complete CHECK (
    (uphill_permille IS NULL AND downhill_permille IS NULL)
    OR (uphill_permille IS NOT NULL AND downhill_permille IS NOT NULL)
  );
COMMENT ON COLUMN mining_road_restriction.uphill_permille IS
  'Qualified maximum uphill grade in travel direction; NULL means unknown';
COMMENT ON COLUMN mining_road_restriction.downhill_permille IS
  'Qualified maximum downhill grade in travel direction; NULL means unknown';
"""

DOWNGRADE = r"""
ALTER TABLE mining_road_restriction
  DROP CONSTRAINT ck_mining_road_grades_complete,
  DROP COLUMN downhill_permille,
  DROP COLUMN uphill_permille;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
