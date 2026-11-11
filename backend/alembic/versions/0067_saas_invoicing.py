"""Facturation SaaS paramétrable (lot 3 commercialisation) — sans activation de paiement.

Revision ID: 0067
Revises: 0066

- `saas_plan` : tarif mensuel paramétrable en GNF (entier, NULL = plan non tarifé) et
  période de facturation (MONTHLY/ANNUAL). Aucun moyen de paiement modélisé.
- `billing_invoice_sequence` : compteur de numérotation par année (table plateforme,
  hors RLS applicative comme `saas_plan`).
- `billing_invoice` : facture d'une société, RLS applicative classique (la société lit
  SES factures ; la plateforme écrit en changeant de contexte, §6.2 point 4). Cycle
  DRAFT → ISSUED → VOIDED (terminal) — aucun encaissement dans l'application.
- `billing_invoice_line` : lignes immuables de la facture (tenant_id NOT NULL, RLS
  SELECT/INSERT), montant = quantité × prix unitaire vérifié en base.
"""

from app.core.migration_tools import run_sql

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None

UPGRADE = r"""
-- 1. Tarification paramétrable du plan (référentiel plateforme, pas de paiement).
ALTER TABLE saas_plan
  ADD COLUMN price_monthly_gnf bigint,
  ADD COLUMN billing_period text,
  ADD CONSTRAINT ck_saas_plan_price CHECK (price_monthly_gnf IS NULL OR price_monthly_gnf >= 0),
  ADD CONSTRAINT ck_saas_plan_period
    CHECK (billing_period IS NULL OR billing_period IN ('MONTHLY', 'ANNUAL'));

-- 2. Numérotation lisible des factures : MF-<année>-<numéro sur 5 chiffres>.
CREATE TABLE billing_invoice_sequence (
  year integer NOT NULL,
  last_number integer NOT NULL DEFAULT 0,
  CONSTRAINT pk_billing_invoice_sequence PRIMARY KEY (year),
  CONSTRAINT ck_bis_year CHECK (year BETWEEN 2000 AND 2999),
  CONSTRAINT ck_bis_last CHECK (last_number >= 0)
);
REVOKE ALL ON billing_invoice_sequence FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON billing_invoice_sequence TO mf_app;

-- 3. Factures (RLS applicative : chaque société ne voit que SES factures).
CREATE TABLE billing_invoice (
  invoice_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  subscription_id uuid,
  number text NOT NULL,
  status text NOT NULL DEFAULT 'DRAFT',
  currency text NOT NULL DEFAULT 'GNF',
  tax_rate_bp integer NOT NULL DEFAULT 0,
  period_start date,
  period_end date,
  subtotal_gnf bigint NOT NULL DEFAULT 0,
  tax_gnf bigint NOT NULL DEFAULT 0,
  total_gnf bigint NOT NULL DEFAULT 0,
  issued_at timestamptz,
  voided_at timestamptz,
  void_reason text,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid,
  updated_by uuid,
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_billing_invoice PRIMARY KEY (invoice_id),
  CONSTRAINT fk_bi__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT fk_bi__subscription FOREIGN KEY (subscription_id)
    REFERENCES tenant_subscription (subscription_id) ON DELETE RESTRICT,
  CONSTRAINT uq_billing_invoice_number UNIQUE (number),
  CONSTRAINT ck_bi_status CHECK (status IN ('DRAFT', 'ISSUED', 'VOIDED')),
  CONSTRAINT ck_bi_currency CHECK (currency = 'GNF'),
  CONSTRAINT ck_bi_tax CHECK (tax_rate_bp BETWEEN 0 AND 10000),
  CONSTRAINT ck_bi_issued CHECK ((status IN ('ISSUED', 'VOIDED')) = (issued_at IS NOT NULL)),
  CONSTRAINT ck_bi_voided CHECK ((status = 'VOIDED') = (voided_at IS NOT NULL)),
  CONSTRAINT ck_bi_void_reason CHECK (void_reason IS NULL OR length(void_reason) BETWEEN 3 AND 500),
  CONSTRAINT ck_bi_amounts CHECK (
    subtotal_gnf >= 0 AND tax_gnf >= 0 AND total_gnf >= 0
    AND tax_gnf <= subtotal_gnf * 10000  -- garde-fou anti-débordement (bp ≤ 10000)
    AND total_gnf = subtotal_gnf + tax_gnf
  ),
  CONSTRAINT ck_bi_period_dates CHECK (period_start IS NULL OR period_end IS NULL OR period_start <= period_end),
  CONSTRAINT ck_bi_notes CHECK (notes IS NULL OR length(notes) <= 500)
);
CREATE INDEX ix_bi_tenant_history ON billing_invoice (tenant_id, created_at DESC);
CREATE INDEX ix_bi_subscription ON billing_invoice (subscription_id) WHERE subscription_id IS NOT NULL;
SELECT app.apply_tenant_rls('billing_invoice', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('billing_invoice');

-- 4. Lignes de facture immuables (lecture seule pour mf_app une fois écrites).
CREATE TABLE billing_invoice_line (
  line_id uuid NOT NULL DEFAULT gen_random_uuid(),
  invoice_id uuid NOT NULL,
  tenant_id uuid NOT NULL,
  line_number smallint NOT NULL,
  description text NOT NULL,
  quantity integer NOT NULL,
  unit_price_gnf bigint NOT NULL,
  amount_gnf bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid,
  CONSTRAINT pk_billing_invoice_line PRIMARY KEY (line_id),
  CONSTRAINT fk_bil__invoice FOREIGN KEY (invoice_id)
    REFERENCES billing_invoice (invoice_id) ON DELETE CASCADE,
  CONSTRAINT fk_bil__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT uq_bil_position UNIQUE (invoice_id, line_number),
  CONSTRAINT ck_bil_position CHECK (line_number BETWEEN 1 AND 50),
  CONSTRAINT ck_bil_description CHECK (length(description) BETWEEN 1 AND 200),
  CONSTRAINT ck_bil_quantity CHECK (quantity BETWEEN 1 AND 100000),
  CONSTRAINT ck_bil_unit_price CHECK (unit_price_gnf >= 0),
  CONSTRAINT ck_bil_amount CHECK (amount_gnf = quantity * unit_price_gnf)
);
CREATE INDEX ix_bil_invoice ON billing_invoice_line (invoice_id, line_number);
SELECT app.apply_tenant_rls('billing_invoice_line', 'SELECT, INSERT');
"""

DOWNGRADE = r"""
DROP TABLE billing_invoice_line;
DROP TABLE billing_invoice;
DROP TABLE billing_invoice_sequence;
ALTER TABLE saas_plan
  DROP CONSTRAINT ck_saas_plan_price,
  DROP CONSTRAINT ck_saas_plan_period,
  DROP COLUMN price_monthly_gnf,
  DROP COLUMN billing_period;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    run_sql(DOWNGRADE)
