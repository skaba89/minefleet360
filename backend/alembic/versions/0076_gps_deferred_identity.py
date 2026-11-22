"""Identité stable des positions téléphone différées, sans activation du rejeu.

Ajout seul : les positions live et traceurs gardent leurs colonnes NULL.
La RLS forcée, les droits INSERT/SELECT et la purge GPS existante restent inchangés.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE fleet_gps_position ADD COLUMN client_point_id uuid;
ALTER TABLE fleet_gps_position ADD COLUMN client_point_fingerprint text;
ALTER TABLE fleet_gps_position ADD CONSTRAINT ck_fgp_deferred_identity CHECK (
  (client_point_id IS NULL AND client_point_fingerprint IS NULL)
  OR (
    client_point_id IS NOT NULL AND client_point_fingerprint IS NOT NULL
    AND source = 'PHONE' AND phone_share_id IS NOT NULL
    AND client_point_fingerprint ~ '^[0-9a-f]{64}$'
  )
);
CREATE UNIQUE INDEX uq_fgp_deferred_identity
  ON fleet_gps_position (tenant_id, phone_share_id, client_point_id)
  WHERE client_point_id IS NOT NULL;
"""

DOWNGRADE = r"""
DROP INDEX uq_fgp_deferred_identity;
ALTER TABLE fleet_gps_position DROP CONSTRAINT ck_fgp_deferred_identity;
ALTER TABLE fleet_gps_position DROP COLUMN client_point_fingerprint;
ALTER TABLE fleet_gps_position DROP COLUMN client_point_id;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
