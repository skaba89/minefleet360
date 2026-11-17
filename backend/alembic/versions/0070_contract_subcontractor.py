"""Rattachement d'un contrat de sous-traitance à son organisation (lot 1, tranche 2b).

Additive : colonne nullable, clé étrangère composite (même tenant), contrainte « rattachement seulement pour un
contrat de type SUBCONTRACTOR ». Le rattachement se fait à la création du brouillon ; les contrats existants restent
sans rattachement (aucune reprise automatique de `counterparty_name`).
"""

from app.core.migration_tools import run_sql

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE legal_contract
  ADD COLUMN subcontractor_id uuid,
  ADD CONSTRAINT fk_legal_contract__subcontractor FOREIGN KEY (tenant_id, subcontractor_id)
    REFERENCES subcontractor (tenant_id, subcontractor_id) ON DELETE RESTRICT,
  ADD CONSTRAINT ck_legal_contract_subcontractor
    CHECK (subcontractor_id IS NULL OR contract_type = 'SUBCONTRACTOR');
CREATE INDEX ix_legal_contract_subcontractor ON legal_contract (tenant_id, subcontractor_id)
  WHERE subcontractor_id IS NOT NULL;
"""

DOWNGRADE = r"""
DROP INDEX ix_legal_contract_subcontractor;
ALTER TABLE legal_contract
  DROP CONSTRAINT ck_legal_contract_subcontractor,
  DROP CONSTRAINT fk_legal_contract__subcontractor,
  DROP COLUMN subcontractor_id;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    run_sql(DOWNGRADE)
