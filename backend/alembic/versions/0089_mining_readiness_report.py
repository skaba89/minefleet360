"""Append-only draft inspection reports; no approval or activation.

Revision ID: 0089
Revises: 0088
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0089"
down_revision = "0088"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE mining_readiness_report (
  report_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  revision_id uuid NOT NULL,
  digest_version text NOT NULL CHECK (digest_version = 'mining-readiness-v1'),
  evidence_digest text NOT NULL CHECK (evidence_digest ~ '^[0-9a-f]{64}$'),
  tolerance_m double precision NOT NULL
    CHECK (tolerance_m >= 0 AND tolerance_m < 'Infinity'::double precision),
  findings jsonb NOT NULL CHECK (jsonb_typeof(findings) = 'array'),
  actor_user_id uuid NOT NULL REFERENCES user_account (user_account_id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, site_id, revision_id)
    REFERENCES mining_route_revision (tenant_id, site_id, revision_id) ON DELETE RESTRICT
);
CREATE INDEX ix_mining_readiness_report_revision
  ON mining_readiness_report (tenant_id, site_id, revision_id, created_at, report_id);
SELECT app.apply_tenant_rls('mining_readiness_report', 'SELECT, INSERT');

CREATE FUNCTION app.check_mining_readiness_report_actor() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER AS $report_actor$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM user_account
      WHERE user_account_id = NEW.actor_user_id AND tenant_id = NEW.tenant_id
  ) THEN
    RAISE EXCEPTION 'report actor unavailable in tenant' USING ERRCODE = '23503';
  END IF;
  RETURN NEW;
END;
$report_actor$;
CREATE TRIGGER trg_mining_readiness_report_actor
  BEFORE INSERT ON mining_readiness_report
  FOR EACH ROW EXECUTE FUNCTION app.check_mining_readiness_report_actor();
COMMENT ON TABLE mining_readiness_report IS
  'Historical technical inspection only; no approval, live closure state or permission to dispatch';
"""

DOWNGRADE = r"""
DROP TABLE mining_readiness_report;
DROP FUNCTION app.check_mining_readiness_report_actor();
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
