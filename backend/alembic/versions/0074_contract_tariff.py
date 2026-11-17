"""Tarifs des contrats de transport (contrôle de gestion, tranche 2a).

Décision du 17 novembre 2026 : revenus par contrat, tarif × quantité MESURÉE. Un tarif s'applique à un contrat
juridique de type TRANSPORT ; modes : tonne mesurée, heure moteur, km, forfait par mission. Table en AJOUT SEUL :
toute révision est une nouvelle version datée (valid_from), la version en vigueur à une date est la plus récente
dont valid_from ≤ date. Additive : aucune table existante modifiée.
"""

from app.core.migration_tools import run_sql

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE contract_tariff (
  contract_tariff_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  contract_id uuid NOT NULL,
  basis text NOT NULL,
  unit_price numeric(18,4) NOT NULL,
  currency text NOT NULL,
  valid_from date NOT NULL,
  note text,
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_contract_tariff PRIMARY KEY (contract_tariff_id),
  CONSTRAINT fk_contract_tariff__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT fk_contract_tariff__contract FOREIGN KEY (tenant_id, contract_id)
    REFERENCES legal_contract (tenant_id, contract_id) ON DELETE RESTRICT,
  CONSTRAINT fk_contract_tariff__author FOREIGN KEY (tenant_id, created_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_contract_tariff_basis CHECK (basis IN ('TONNE','HOUR','KM','MISSION')),
  CONSTRAINT ck_contract_tariff_price CHECK (unit_price > 0),
  CONSTRAINT ck_contract_tariff_currency CHECK (currency ~ '^[A-Z]{3}$'),
  CONSTRAINT ck_contract_tariff_note CHECK (note IS NULL OR char_length(note) <= 500),
  CONSTRAINT uq_contract_tariff_version UNIQUE (tenant_id, contract_id, valid_from)
);
SELECT app.apply_tenant_rls('contract_tariff', 'SELECT, INSERT');
CREATE TRIGGER tg_contract_tariff_append_only BEFORE UPDATE OR DELETE ON contract_tariff
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
"""

DOWNGRADE = r"""
DROP TABLE contract_tariff;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    run_sql(DOWNGRADE)
