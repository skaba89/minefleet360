"""Prepare auditable contract review states without enabling API updates.

Revision ID: 0047
Revises: 0046
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE legal_contract
  DROP CONSTRAINT ck_legal_contract_status,
  ADD COLUMN submitted_at timestamptz,
  ADD COLUMN reviewed_by uuid,
  ADD COLUMN reviewed_at timestamptz,
  ADD COLUMN review_note text,
  ADD CONSTRAINT ck_legal_contract_status CHECK (
    status IN ('DRAFT', 'PENDING_REVIEW', 'APPROVED', 'REJECTED')
  ),
  ADD CONSTRAINT ck_legal_contract_review_consistency CHECK (
    (status = 'DRAFT' AND submitted_at IS NULL AND reviewed_by IS NULL AND reviewed_at IS NULL)
    OR (status = 'PENDING_REVIEW' AND submitted_at IS NOT NULL
        AND document_sha256 IS NOT NULL AND reviewed_by IS NULL AND reviewed_at IS NULL)
    OR (status IN ('APPROVED', 'REJECTED') AND submitted_at IS NOT NULL
        AND document_sha256 IS NOT NULL AND reviewed_by IS NOT NULL
        AND reviewed_at IS NOT NULL AND reviewed_by <> created_by)
  );
CREATE INDEX ix_legal_contract_review_queue
  ON legal_contract (tenant_id, site_id, status);
-- No UPDATE RLS grant yet: transitions are not exposed before RBAC and audit are implemented.
"""
DOWNGRADE = r"""
UPDATE legal_contract SET status = 'DRAFT', submitted_at = NULL,
  reviewed_by = NULL, reviewed_at = NULL, review_note = NULL
WHERE status <> 'DRAFT';
ALTER TABLE legal_contract
  DROP CONSTRAINT ck_legal_contract_review_consistency,
  DROP CONSTRAINT ck_legal_contract_status,
  DROP COLUMN submitted_at,
  DROP COLUMN reviewed_by,
  DROP COLUMN reviewed_at,
  DROP COLUMN review_note,
  ADD CONSTRAINT ck_legal_contract_status CHECK (status = 'DRAFT');
DROP INDEX ix_legal_contract_review_queue;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
