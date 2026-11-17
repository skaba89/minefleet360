"""Rattachement facultatif d'une mission à un contrat de transport (contrôle de gestion, tranche 2b).

Additive : colonne nullable, aucune donnée existante modifiée. Le contrat doit être un contrat TRANSPORT
approuvé du même site (contrôlé par l'API) ; la clé étrangère composite garantit le même tenant.
"""

from app.core.migration_tools import run_sql

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE mission
  ADD COLUMN contract_id uuid,
  ADD CONSTRAINT fk_mission__contract FOREIGN KEY (tenant_id, contract_id)
    REFERENCES legal_contract (tenant_id, contract_id) ON DELETE RESTRICT;
CREATE INDEX ix_mission_contract ON mission (tenant_id, contract_id) WHERE contract_id IS NOT NULL;
"""

DOWNGRADE = r"""
DROP INDEX ix_mission_contract;
ALTER TABLE mission DROP CONSTRAINT fk_mission__contract, DROP COLUMN contract_id;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    run_sql(DOWNGRADE)
