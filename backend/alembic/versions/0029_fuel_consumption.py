"""Repères de plein complet pour calculer les consommations par intervalle.

Revision ID: 0029
Revises: 0028
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE fuel_issue ADD COLUMN full_tank boolean NOT NULL DEFAULT false;
"""

DOWNGRADE = r"""
ALTER TABLE fuel_issue DROP COLUMN full_tank;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
