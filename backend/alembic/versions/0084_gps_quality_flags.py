"""Flags de qualité GPS §1.3 sur l'historique de positions : tardif et décalage.

Revision ID: 0084
Revises: 0083
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE fleet_gps_position ADD COLUMN late BOOLEAN;
ALTER TABLE fleet_gps_position ADD COLUMN clock_skew_suspect BOOLEAN;
COMMENT ON COLUMN fleet_gps_position.late IS
  '§1.3 : reçu plus de gps_late_threshold_seconds après l''horodatage appareil';
COMMENT ON COLUMN fleet_gps_position.clock_skew_suspect IS
  '§1.3 : écart |received_at - recorded_at| hors tolérance configurable';
"""

DOWNGRADE = r"""
ALTER TABLE fleet_gps_position DROP COLUMN clock_skew_suspect;
ALTER TABLE fleet_gps_position DROP COLUMN late;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
