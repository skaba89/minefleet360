"""Rattachement d'un conducteur sous-traitant à son organisation (lot 1, tranche 2c).

Additive : colonne nullable, clé étrangère composite (même tenant), contrainte « rattachement seulement pour un
conducteur SUBCONTRACTOR ». Donnée RH : exposée au seul rôle HR (field_policies), jamais journalisée en valeur.
Les conducteurs existants restent sans rattachement (aucune reprise automatique de `external_company_name`).
"""

from app.core.migration_tools import run_sql

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE driver
  ADD COLUMN subcontractor_id uuid,
  ADD CONSTRAINT fk_driver__subcontractor FOREIGN KEY (tenant_id, subcontractor_id)
    REFERENCES subcontractor (tenant_id, subcontractor_id) ON DELETE RESTRICT,
  ADD CONSTRAINT ck_driver_subcontractor CHECK (subcontractor_id IS NULL OR employment_type = 'SUBCONTRACTOR');
CREATE INDEX ix_driver_subcontractor ON driver (tenant_id, subcontractor_id) WHERE subcontractor_id IS NOT NULL;
"""

DOWNGRADE = r"""
DROP INDEX ix_driver_subcontractor;
ALTER TABLE driver
  DROP CONSTRAINT ck_driver_subcontractor,
  DROP CONSTRAINT fk_driver__subcontractor,
  DROP COLUMN subcontractor_id;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    run_sql(DOWNGRADE)
