"""Append-only evidence of a technical inspection of a draft network."""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0089"
down_revision = "0088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(
        """
        CREATE TABLE mining_draft_inspection_report (
          report_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id uuid NOT NULL,
          site_id uuid NOT NULL,
          revision_id uuid NOT NULL,
          inspected_by uuid NOT NULL,
          inspected_at timestamptz NOT NULL,
          validator_version integer NOT NULL CHECK (validator_version > 0),
          tolerance_m double precision NOT NULL CHECK (tolerance_m >= 0 AND tolerance_m < 'Infinity'),
          evidence_sha256 bytea NOT NULL CHECK (octet_length(evidence_sha256) = 32),
          evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'array'),
          findings jsonb NOT NULL CHECK (jsonb_typeof(findings) = 'array'),
          FOREIGN KEY (tenant_id, site_id, revision_id)
            REFERENCES mining_route_revision (tenant_id, site_id, revision_id) ON DELETE RESTRICT,
          FOREIGN KEY (tenant_id, inspected_by)
            REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
          UNIQUE (tenant_id, site_id, revision_id, inspected_by, validator_version, tolerance_m, evidence_sha256)
        );
        CREATE TRIGGER tg_report_append_only BEFORE UPDATE OR DELETE ON mining_draft_inspection_report
          FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
        SELECT app.apply_tenant_rls('mining_draft_inspection_report', 'SELECT, INSERT');
        """
    )


def downgrade() -> None:
    guard_destructive()
    run_sql("DROP TABLE mining_draft_inspection_report;")
