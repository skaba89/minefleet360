"""Enable guarded verified status with tenant RLS and evidence constraints.

Revision ID: 0051
Revises: 0050
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE legal_contract_document
  DROP CONSTRAINT ck_legal_contract_document_status,
  DROP CONSTRAINT ck_legal_contract_document_verified,
  ADD CONSTRAINT ck_legal_contract_document_status
    CHECK (status IN ('PENDING', 'VERIFIED')),
  ADD CONSTRAINT ck_legal_contract_document_verified CHECK (
    (status = 'PENDING' AND verified_at IS NULL
      AND NOT stored_object_verified AND NOT malware_scan_passed)
    OR
    (status = 'VERIFIED' AND verified_at IS NOT NULL
      AND stored_object_verified AND malware_scan_passed)
  );
SELECT app.apply_tenant_rls('legal_contract_document', 'SELECT, INSERT, UPDATE');
"""

DOWNGRADE = r"""
UPDATE legal_contract_document SET status = 'PENDING',
  stored_object_verified = false, malware_scan_passed = false, verified_at = NULL
WHERE status = 'VERIFIED';
ALTER TABLE legal_contract_document
  DROP CONSTRAINT ck_legal_contract_document_status,
  DROP CONSTRAINT ck_legal_contract_document_verified,
  ADD CONSTRAINT ck_legal_contract_document_status CHECK (status = 'PENDING'),
  ADD CONSTRAINT ck_legal_contract_document_verified CHECK (
    status = 'PENDING' AND verified_at IS NULL
    AND NOT stored_object_verified AND NOT malware_scan_passed
  );
SELECT app.apply_tenant_rls('legal_contract_document', 'SELECT, INSERT');
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
