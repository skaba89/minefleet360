"""Tenant-isolated foundations for contracts and insurance policy register.

Revision ID: 0046
Revises: 0045
No electronic signature is issued by this migration.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE legal_contract (
  contract_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  reference text NOT NULL,
  title text NOT NULL,
  contract_type text NOT NULL,
  counterparty_name text NOT NULL,
  status text NOT NULL DEFAULT 'DRAFT',
  document_sha256 text,
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_legal_contract_site FOREIGN KEY (tenant_id, site_id)
    REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT uq_legal_contract_tenant_id UNIQUE (tenant_id, contract_id),
  CONSTRAINT uq_legal_contract_reference UNIQUE (tenant_id, reference),
  CONSTRAINT ck_legal_contract_reference CHECK (char_length(trim(reference)) BETWEEN 1 AND 120),
  CONSTRAINT ck_legal_contract_title CHECK (char_length(trim(title)) BETWEEN 1 AND 240),
  CONSTRAINT ck_legal_contract_counterparty CHECK (char_length(trim(counterparty_name)) BETWEEN 1 AND 240),
  CONSTRAINT ck_legal_contract_type CHECK (contract_type IN
    ('SUPPLIER','TRANSPORT','SUBCONTRACTOR','EMPLOYMENT','LEASE','OTHER')),
  CONSTRAINT ck_legal_contract_status CHECK (status = 'DRAFT'),
  CONSTRAINT ck_legal_contract_hash CHECK
    (document_sha256 IS NULL OR document_sha256 ~ '^[0-9a-f]{64}$')
);
CREATE INDEX ix_legal_contract_site ON legal_contract (tenant_id, site_id);
SELECT app.apply_tenant_rls('legal_contract', 'SELECT, INSERT');

CREATE TABLE insurance_policy (
  insurance_policy_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  policy_number text NOT NULL,
  insurer_name text NOT NULL,
  coverage_type text NOT NULL,
  coverage_start date NOT NULL,
  coverage_end date NOT NULL,
  premium_amount numeric(18,2),
  currency text NOT NULL DEFAULT 'GNF',
  contract_id uuid,
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_insurance_policy_site FOREIGN KEY (tenant_id, site_id)
    REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_insurance_policy_contract FOREIGN KEY (tenant_id, contract_id)
    REFERENCES legal_contract (tenant_id, contract_id) ON DELETE RESTRICT,
  CONSTRAINT uq_insurance_policy_number UNIQUE (tenant_id, policy_number),
  CONSTRAINT ck_insurance_policy_number CHECK (char_length(trim(policy_number)) BETWEEN 1 AND 120),
  CONSTRAINT ck_insurance_insurer CHECK (char_length(trim(insurer_name)) BETWEEN 1 AND 240),
  CONSTRAINT ck_insurance_dates CHECK (coverage_end >= coverage_start),
  CONSTRAINT ck_insurance_premium CHECK (premium_amount IS NULL OR premium_amount >= 0),
  CONSTRAINT ck_insurance_currency CHECK (currency = 'GNF'),
  CONSTRAINT ck_insurance_coverage CHECK (coverage_type IN
    ('FLEET','VEHICLE','CARGO','LIABILITY','EMPLOYEE','EQUIPMENT','OTHER'))
);
CREATE INDEX ix_insurance_expiry ON insurance_policy (tenant_id, coverage_end);
CREATE INDEX ix_insurance_site ON insurance_policy (tenant_id, site_id);
SELECT app.apply_tenant_rls('insurance_policy', 'SELECT, INSERT');
"""

DOWNGRADE = r"""
DROP TABLE insurance_policy;
DROP TABLE legal_contract;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
