"""Budget prévisionnel des coûts par site × mois × composante (contrôle de gestion, tranche 1).

Décision du 17 novembre 2026 (propriétaire du projet) : granularité site × mois × composante (carburant, pièces,
main-d'œuvre, pneumatiques). Table en AJOUT SEUL : chaque révision est une nouvelle version, la plus récente fait foi
(traçabilité complète des révisions budgétaires). Additive : aucune table existante modifiée.
"""

from app.core.migration_tools import run_sql

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE cost_budget (
  cost_budget_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  budget_month date NOT NULL,
  component text NOT NULL,
  amount numeric(18,2) NOT NULL,
  currency text NOT NULL,
  note text,
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_cost_budget PRIMARY KEY (cost_budget_id),
  CONSTRAINT fk_cost_budget__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_budget__site FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_budget__author FOREIGN KEY (tenant_id, created_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_cost_budget_month CHECK (extract(day FROM budget_month) = 1),
  CONSTRAINT ck_cost_budget_component CHECK (component IN ('FUEL','PARTS','LABOUR','TYRES')),
  CONSTRAINT ck_cost_budget_amount CHECK (amount >= 0),
  CONSTRAINT ck_cost_budget_currency CHECK (currency ~ '^[A-Z]{3}$'),
  CONSTRAINT ck_cost_budget_note CHECK (note IS NULL OR char_length(note) <= 500)
);
CREATE INDEX ix_cost_budget_scope ON cost_budget (tenant_id, site_id, budget_month, component, created_at DESC);
SELECT app.apply_tenant_rls('cost_budget', 'SELECT, INSERT');
CREATE TRIGGER tg_cost_budget_append_only BEFORE UPDATE OR DELETE ON cost_budget
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
"""

DOWNGRADE = r"""
DROP TABLE cost_budget;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    run_sql(DOWNGRADE)
