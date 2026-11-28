"""Survey tolerance qualification; historical value binding, never an approval.

Revision ID: 0091
Revises: 0090
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE mining_tolerance_qualification (
  qualification_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  CONSTRAINT fk_mining_tol_qual__site
    FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  tolerance_m double precision NOT NULL
    CHECK (tolerance_m >= 0 AND tolerance_m < 'Infinity'::double precision),
  survey_source text NOT NULL CHECK (char_length(btrim(survey_source)) BETWEEN 1 AND 100),
  measurement_method text NOT NULL CHECK (char_length(btrim(measurement_method)) BETWEEN 1 AND 100),
  instrument_precision_m double precision NOT NULL
    CHECK (instrument_precision_m >= 0 AND instrument_precision_m < 'Infinity'::double precision),
  surveyed_on date NOT NULL CHECK (surveyed_on <= CURRENT_DATE),
  responsible_user_id uuid NOT NULL REFERENCES user_account (user_account_id) ON DELETE RESTRICT,
  referential_version text NOT NULL CHECK (char_length(btrim(referential_version)) BETWEEN 1 AND 100),
  justification text NOT NULL CHECK (char_length(btrim(justification)) BETWEEN 1 AND 500),
  status text NOT NULL DEFAULT 'PROPOSED' CHECK (status IN ('PROPOSED', 'APPROVED', 'RETIRED')),
  proposed_by uuid NOT NULL REFERENCES user_account (user_account_id) ON DELETE RESTRICT,
  approved_by uuid REFERENCES user_account (user_account_id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  approved_at timestamptz,
  retired_at timestamptz
);
SELECT app.apply_tenant_rls('mining_tolerance_qualification', 'SELECT, INSERT, UPDATE');
CREATE INDEX ix_mining_tol_qual_site
  ON mining_tolerance_qualification (tenant_id, site_id, status, tolerance_m);

CREATE FUNCTION app.check_mining_tolerance_qualification() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER AS $tol_qual$
BEGIN
  IF TG_OP = 'UPDATE' AND (
    NEW.tolerance_m, NEW.survey_source, NEW.measurement_method, NEW.instrument_precision_m,
    NEW.surveyed_on, NEW.referential_version, NEW.justification, NEW.proposed_by, NEW.created_at
  ) IS DISTINCT FROM (
    OLD.tolerance_m, OLD.survey_source, OLD.measurement_method, OLD.instrument_precision_m,
    OLD.surveyed_on, OLD.referential_version, OLD.justification, OLD.proposed_by, OLD.created_at
  ) THEN
    RAISE EXCEPTION 'qualification survey fields are immutable' USING ERRCODE = '23514';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM user_account
      WHERE tenant_id = NEW.tenant_id AND user_account_id = NEW.proposed_by
  ) OR NOT EXISTS (
    SELECT 1 FROM user_account
      WHERE tenant_id = NEW.tenant_id AND user_account_id = NEW.responsible_user_id
  ) OR (NEW.approved_by IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM user_account
      WHERE tenant_id = NEW.tenant_id AND user_account_id = NEW.approved_by
  )) THEN
    RAISE EXCEPTION 'qualification actor unavailable in tenant' USING ERRCODE = '23503';
  END IF;
  IF NEW.status = 'APPROVED' AND (
    NEW.approved_by IS NULL OR NEW.approved_at IS NULL
    OR NEW.approved_by = NEW.proposed_by OR NEW.approved_by = NEW.responsible_user_id
  ) THEN
    RAISE EXCEPTION 'tolerance approval requires an independent approver' USING ERRCODE = '23514';
  END IF;
  IF NEW.status = 'RETIRED' AND NEW.retired_at IS NULL THEN
    RAISE EXCEPTION 'retired tolerance requires a retirement date' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$tol_qual$;
CREATE TRIGGER trg_mining_tolerance_qualification
  BEFORE INSERT OR UPDATE ON mining_tolerance_qualification
  FOR EACH ROW EXECUTE FUNCTION app.check_mining_tolerance_qualification();

ALTER TABLE mining_readiness_report ADD COLUMN tolerance_qualification_id uuid
  REFERENCES mining_tolerance_qualification (qualification_id) ON DELETE RESTRICT;

CREATE FUNCTION app.check_mining_readiness_report_tolerance() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER AS $report_tol$
DECLARE
  qual record;
BEGIN
  IF NEW.tolerance_qualification_id IS NULL THEN
    RETURN NEW;
  END IF;
  SELECT tenant_id, site_id, status, tolerance_m INTO qual FROM mining_tolerance_qualification
    WHERE qualification_id = NEW.tolerance_qualification_id;
  IF NOT FOUND OR qual.tenant_id <> NEW.tenant_id OR qual.site_id <> NEW.site_id
    OR qual.status <> 'APPROVED' OR qual.tolerance_m <> NEW.tolerance_m THEN
    RAISE EXCEPTION 'report tolerance not qualified for this site' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$report_tol$;
CREATE TRIGGER trg_mining_readiness_report_tolerance
  BEFORE INSERT ON mining_readiness_report
  FOR EACH ROW EXECUTE FUNCTION app.check_mining_readiness_report_tolerance();
COMMENT ON TABLE mining_tolerance_qualification IS
  'Site-survey tolerance qualification; provenance, method and independent approval; no universal tolerance';
COMMENT ON COLUMN mining_readiness_report.tolerance_qualification_id IS
  'Approved survey tolerance this report was computed with; historical binding, current state checked by the service';
"""

DOWNGRADE = r"""
DROP TRIGGER trg_mining_readiness_report_tolerance ON mining_readiness_report;
DROP FUNCTION app.check_mining_readiness_report_tolerance();
ALTER TABLE mining_readiness_report DROP COLUMN tolerance_qualification_id;
DROP TABLE mining_tolerance_qualification;
DROP FUNCTION app.check_mining_tolerance_qualification();
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
