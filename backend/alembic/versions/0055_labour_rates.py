"""Coût complet par engin (chantier D) : taux horaires de main-d'œuvre datés, en ajout seul.

Revision ID: 0055
Revises: 0054

Voir docs/LIVRAISON_COUT_COMPLET.md. Sans taux saisi, la main-d'œuvre n'est jamais valorisée (« Données
insuffisantes »). Un taux s'applique à partir de sa date d'effet ; le taux d'un site prime sur le taux société
(site_id NULL). Une erreur se corrige par un nouveau taux daté : l'historique des valorisations reste reproductible.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE maintenance_labour_rate (
  maintenance_labour_rate_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid,
  hourly_rate numeric(16,2) NOT NULL,
  currency text NOT NULL,
  valid_from date NOT NULL,
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_maintenance_labour_rate PRIMARY KEY (maintenance_labour_rate_id),
  CONSTRAINT fk_mlr__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT fk_mlr__site FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_mlr__author FOREIGN KEY (tenant_id, created_by) REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_mlr_rate CHECK (hourly_rate > 0),
  CONSTRAINT ck_mlr_currency CHECK (currency ~ '^[A-Z]{3}$')
);
CREATE UNIQUE INDEX uq_mlr_scope_date
  ON maintenance_labour_rate (tenant_id, coalesce(site_id, '00000000-0000-0000-0000-000000000000'::uuid), valid_from);
SELECT app.apply_tenant_rls('maintenance_labour_rate', 'SELECT, INSERT');
CREATE TRIGGER tg_maintenance_labour_rate_append_only BEFORE UPDATE OR DELETE ON maintenance_labour_rate
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
"""

DOWNGRADE = r"""
DROP TABLE maintenance_labour_rate;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
