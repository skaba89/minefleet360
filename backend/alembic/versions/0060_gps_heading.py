"""Cap mesuré des positions GPS (degrés, 0 = nord, sens horaire).

Revision ID: 0060
Revises: 0059

Le cap n'est enregistré que s'il est **envoyé** par l'équipement (traceur, téléphone) : il n'est jamais calculé
puis présenté comme mesuré. Colonne facultative sans valeur par défaut : ajout instantané, sans réécriture de la
table (en ajout seul). Voir docs/GPS_LIVE_MAP.md.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(
        "ALTER TABLE fleet_gps_position ADD COLUMN heading_deg real, "
        "ADD CONSTRAINT ck_fgp_heading CHECK (heading_deg IS NULL OR (heading_deg >= 0 AND heading_deg < 360))"
    )


def downgrade() -> None:
    guard_destructive()
    run_sql("ALTER TABLE fleet_gps_position DROP CONSTRAINT ck_fgp_heading, DROP COLUMN heading_deg")
