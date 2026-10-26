"""Conserve les empreintes des refresh consommés pendant la durée de vie d'une session.

Revision ID: 0009
Revises: 0008

La colonne précédente reste lisible : les sessions existantes conservent leur dernier refresh
consommé avant l'upgrade. L'application l'intègre à l'historique lors de la rotation suivante.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE auth_session
  ADD COLUMN consumed_refresh_hashes bytea[] NOT NULL DEFAULT '{}'::bytea[],
  ADD CONSTRAINT ck_auth_session_consumed_refresh_bound
    CHECK (cardinality(consumed_refresh_hashes) <= 1024);
"""

DOWNGRADE = r"""
ALTER TABLE auth_session
  DROP CONSTRAINT ck_auth_session_consumed_refresh_bound,
  DROP COLUMN consumed_refresh_hashes;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
