"""Grant UPDATE to mf_app on spare_part_replenishment (submit/decision flows).

Migration 0042 granted only SELECT, INSERT while the raw UPDATE of the submit and
decision endpoints arrived with 0044: any call to
`POST /part-replenishments/{id}/submit` or `/decision` failed with 42501
(INTERNAL_ERROR 500) because mf_app lacked the UPDATE privilege. The backend tests
only asserted the 403 paths, never the happy path, so the regression slipped through.

Revision ID: 0064
Revises: 0063
"""

from app.core.migration_tools import run_sql

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

UPGRADE = r"""
-- Ré-applique la policy RLS (identique) et accorde UPDATE à mf_app sur la table.
SELECT app.apply_tenant_rls('spare_part_replenishment', 'SELECT, INSERT, UPDATE');
"""

DOWNGRADE = r"""
SELECT app.apply_tenant_rls('spare_part_replenishment', 'SELECT, INSERT');
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    run_sql(DOWNGRADE)
