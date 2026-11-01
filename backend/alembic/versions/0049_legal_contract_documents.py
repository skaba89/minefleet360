"""Tenant-scoped registry for future contract document verification.

Revision ID: 0049
Revises: 0048
Files are NOT uploaded or verified by this migration.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE legal_contract_document (
  document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  contract_id uuid NOT NULL,
  sha256 text NOT NULL,
  object_key text NOT NULL,
  original_filename text NOT NULL,
  content_type text NOT NULL,
  byte_size bigint NOT NULL,
  status text NOT NULL DEFAULT 'PENDING',
  uploaded_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_legal_contract_document_contract
    FOREIGN KEY (tenant_id, contract_id)
    REFERENCES legal_contract (tenant_id, contract_id) ON DELETE RESTRICT,
  CONSTRAINT uq_legal_contract_document_object UNIQUE (tenant_id, object_key),
  CONSTRAINT ck_legal_contract_document_hash CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_legal_contract_document_key CHECK (char_length(trim(object_key)) BETWEEN 1 AND 512),
  CONSTRAINT ck_legal_contract_document_name
    CHECK (char_length(trim(original_filename)) BETWEEN 1 AND 255),
  CONSTRAINT ck_legal_contract_document_type
    CHECK (content_type IN ('application/pdf')),
  CONSTRAINT ck_legal_contract_document_size
    CHECK (byte_size BETWEEN 1 AND 26214400),
  CONSTRAINT ck_legal_contract_document_status CHECK (status = 'PENDING')
);
CREATE INDEX ix_legal_contract_document_contract
  ON legal_contract_document (tenant_id, contract_id);
SELECT app.apply_tenant_rls('legal_contract_document', 'SELECT, INSERT');
"""

DOWNGRADE = r"""
DROP TABLE legal_contract_document;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
