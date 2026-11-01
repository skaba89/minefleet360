"""Allow guarded contract submission updates.

Revision ID: 0048
Revises: 0047
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None

UPGRADE = r"""
SELECT app.apply_tenant_rls('legal_contract', 'SELECT, INSERT, UPDATE');
"""
DOWNGRADE = r"""
SELECT app.apply_tenant_rls('legal_contract', 'SELECT, INSERT');
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
