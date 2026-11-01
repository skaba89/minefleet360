"""Prepare proof fields for verified contract documents.

Revision ID: 0050
Revises: 0049
No service is permitted to mark documents verified yet.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE legal_contract_document
  DROP CONSTRAINT ck_legal_contract_document_status,
  ADD COLUMN stored_object_verified boolean NOT NULL DEFAULT false,
  ADD COLUMN malware_scan_passed boolean NOT NULL DEFAULT false,
  ADD COLUMN verified_at timestamptz,
  ADD CONSTRAINT ck_legal_contract_document_status CHECK (
    status IN ('PENDING', 'VERIFIED', 'REJECTED')
  ),
  ADD CONSTRAINT ck_legal_contract_document_verified CHECK (
    (status = 'PENDING' AND verified_at IS NULL
      AND NOT stored_object_verified AND NOT malware_scan_passed)
    OR (status = 'VERIFIED' AND verified_at IS NOT NULL
      AND stored_object_verified AND malware_scan_passed)
    OR (status = 'REJECTED' AND verified_at IS NULL)
  );
-- The app role retains SELECT, INSERT only. No verification endpoint exists.
"""
DOWNGRADE = r"""
UPDATE legal_contract_document
  SET status = 'PENDING', verified_at = NULL,
      stored_object_verified = false, malware_scan_passed = false
WHERE status <> 'PENDING';
ALTER TABLE legal_contract_document
  DROP CONSTRAINT ck_legal_contract_document_verified,
  DROP CONSTRAINT ck_legal_contract_document_status,
  DROP COLUMN stored_object_verified,
  DROP COLUMN malware_scan_passed,
  DROP COLUMN verified_at,
  ADD CONSTRAINT ck_legal_contract_document_status CHECK (status = 'PENDING');
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
