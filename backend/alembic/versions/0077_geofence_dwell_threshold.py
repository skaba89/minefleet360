"""Optional, per-geofence stationary-dwell threshold; never activates alerts.

Revision ID: 0077
Revises: 0076

NULL means disabled, including for all pre-existing zones. The existing site_geofence
RLS, audit/touch triggers, tenant/site relations and GPS ingestion remain unchanged.
"""
from app.core.migration_tools import guard_destructive, run_sql

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE site_geofence
  ADD COLUMN dwell_threshold_minutes integer,
  ADD CONSTRAINT ck_sgf_dwell_threshold_minutes
    CHECK (dwell_threshold_minutes BETWEEN 1 AND 1440);
"""

DOWNGRADE = r"""
ALTER TABLE site_geofence
  DROP CONSTRAINT ck_sgf_dwell_threshold_minutes,
  DROP COLUMN dwell_threshold_minutes;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
