"""Rattachement d'un engin sous-traité à son organisation sous-traitante (lot 1, tranche 2).

Additive : colonne nullable, clé étrangère composite (même tenant), contrainte « rattachement seulement pour un engin
SUBCONTRACTED ». Les engins existants restent sans rattachement (aucune reprise automatique du texte libre).
"""

from app.core.migration_tools import run_sql

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE vehicle
  ADD COLUMN subcontractor_id uuid,
  ADD CONSTRAINT fk_vehicle__subcontractor FOREIGN KEY (tenant_id, subcontractor_id)
    REFERENCES subcontractor (tenant_id, subcontractor_id) ON DELETE RESTRICT,
  ADD CONSTRAINT ck_vehicle_subcontractor CHECK (subcontractor_id IS NULL OR ownership_type = 'SUBCONTRACTED');
CREATE INDEX ix_vehicle_subcontractor ON vehicle (tenant_id, subcontractor_id) WHERE subcontractor_id IS NOT NULL;
"""

DOWNGRADE = r"""
DROP INDEX ix_vehicle_subcontractor;
ALTER TABLE vehicle
  DROP CONSTRAINT ck_vehicle_subcontractor,
  DROP CONSTRAINT fk_vehicle__subcontractor,
  DROP COLUMN subcontractor_id;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    run_sql(DOWNGRADE)
