"""Historical review decisions, never operational authorization.

Revision ID: 0090
Revises: 0089
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE mining_readiness_report ADD CONSTRAINT uq_mining_report_review_scope
  UNIQUE (tenant_id, site_id, revision_id, report_id);
CREATE TABLE mining_review_decision (
  decision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  revision_id uuid NOT NULL,
  report_id uuid NOT NULL,
  stage text NOT NULL CHECK (stage IN ('TECHNICAL', 'HSE')),
  decision text NOT NULL CHECK (decision IN ('APPROVED', 'REJECTED')),
  actor_user_id uuid NOT NULL REFERENCES user_account (user_account_id) ON DELETE RESTRICT,
  reason text NOT NULL CHECK (char_length(btrim(reason)) BETWEEN 1 AND 500),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (report_id, stage),
  FOREIGN KEY (tenant_id, site_id, revision_id, report_id)
    REFERENCES mining_readiness_report (tenant_id, site_id, revision_id, report_id) ON DELETE RESTRICT
);
SELECT app.apply_tenant_rls('mining_review_decision', 'SELECT, INSERT');

CREATE FUNCTION app.check_mining_review_decision() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER AS $review$
DECLARE
  author_id uuid;
  finding_total integer;
  technical_actor uuid;
BEGIN
  SELECT actor_user_id, jsonb_array_length(findings)
    INTO author_id, finding_total FROM mining_readiness_report
    WHERE tenant_id = NEW.tenant_id AND site_id = NEW.site_id
      AND revision_id = NEW.revision_id AND report_id = NEW.report_id;
  IF NOT FOUND OR NOT EXISTS (
    SELECT 1 FROM user_account
      WHERE tenant_id = NEW.tenant_id AND user_account_id = NEW.actor_user_id
  ) THEN
    RAISE EXCEPTION 'review reference outside tenant or site' USING ERRCODE = '23503';
  END IF;
  IF author_id = NEW.actor_user_id OR (NEW.decision = 'APPROVED' AND finding_total <> 0) THEN
    RAISE EXCEPTION 'review prerequisites not satisfied' USING ERRCODE = '23514';
  END IF;
  IF NEW.stage = 'HSE' THEN
    SELECT actor_user_id INTO technical_actor FROM mining_review_decision
      WHERE tenant_id = NEW.tenant_id AND site_id = NEW.site_id
        AND revision_id = NEW.revision_id AND report_id = NEW.report_id
        AND stage = 'TECHNICAL' AND decision = 'APPROVED';
    IF NOT FOUND OR technical_actor = NEW.actor_user_id OR technical_actor = author_id THEN
      RAISE EXCEPTION 'independent technical approval required' USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END;
$review$;
CREATE TRIGGER trg_mining_review_decision
  BEFORE INSERT ON mining_review_decision
  FOR EACH ROW EXECUTE FUNCTION app.check_mining_review_decision();
COMMENT ON TABLE mining_review_decision IS
  'Historical decisions only; current evidence, role and activation checks belong to the service';
"""

DOWNGRADE = r"""
DROP TABLE mining_review_decision;
DROP FUNCTION app.check_mining_review_decision();
ALTER TABLE mining_readiness_report DROP CONSTRAINT uq_mining_report_review_scope;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
