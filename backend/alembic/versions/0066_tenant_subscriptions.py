"""Abonnements SaaS (lot 2 commercialisation) — rattachement plan↔société et cycle de vie.

Revision ID: 0066
Revises: 0065

- `tenant_subscription` : un abonnement par société à la fois (index unique partiel sur les
  statuts « vivants » TRIAL/ACTIVE/SUSPENDED) ; CANCELLED est terminal et libère le créneau.
- Table RLS-applicative classique (tenant_id NOT NULL, policy tenant_isolation) : la société
  lit SON abonnement ; la plateforme écrit en changeant de contexte (§6.2 point 4, audité).
- Pas de paiement, pas de tarif : le lot 3 (facturation paramétrable) viendra après arbitrage.
  `period_ends_at` est informatif à ce stade (renouvellement manuel par la plateforme).
"""

from app.core.migration_tools import run_sql

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE tenant_subscription (
  subscription_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  plan_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'TRIAL',
  trial_ends_at timestamptz,
  period_ends_at timestamptz,
  suspended_at timestamptz,
  cancelled_at timestamptz,
  suspension_reason text,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid,
  updated_by uuid,
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_tenant_subscription PRIMARY KEY (subscription_id),
  CONSTRAINT fk_ts__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT fk_ts__plan FOREIGN KEY (plan_id) REFERENCES saas_plan (plan_id) ON DELETE RESTRICT,
  CONSTRAINT ck_ts_status CHECK (status IN ('TRIAL', 'ACTIVE', 'SUSPENDED', 'CANCELLED')),
  CONSTRAINT ck_ts_trial_ends CHECK (trial_ends_at IS NULL OR trial_ends_at > created_at),
  CONSTRAINT ck_ts_period_ends CHECK (period_ends_at IS NULL OR period_ends_at > created_at),
  CONSTRAINT ck_ts_suspended CHECK ((status = 'SUSPENDED') = (suspended_at IS NOT NULL)),
  CONSTRAINT ck_ts_cancelled CHECK ((status = 'CANCELLED') = (cancelled_at IS NOT NULL)),
  CONSTRAINT ck_ts_reason CHECK (suspension_reason IS NULL OR length(suspension_reason) BETWEEN 3 AND 500),
  CONSTRAINT ck_ts_notes CHECK (notes IS NULL OR length(notes) <= 500)
);
CREATE UNIQUE INDEX uq_ts_tenant_current ON tenant_subscription (tenant_id)
  WHERE status IN ('TRIAL', 'ACTIVE', 'SUSPENDED');
CREATE INDEX ix_ts_tenant_history ON tenant_subscription (tenant_id, created_at DESC);
SELECT app.apply_tenant_rls('tenant_subscription', 'SELECT, INSERT, UPDATE');
-- Déclencheur tg_touch : updated_at + row_version incrémentés en base (DB-24), requis par AuditedColumns.
SELECT app.apply_touch('tenant_subscription');
"""

DOWNGRADE = r"""
DROP TABLE tenant_subscription;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    run_sql(DOWNGRADE)
