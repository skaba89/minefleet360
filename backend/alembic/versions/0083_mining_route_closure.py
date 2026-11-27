"""Time-bounded mining road closures; no routing activation.

Revision ID: 0083
Revises: 0082
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE mining_route_closure (
  closure_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  revision_id uuid NOT NULL,
  segment_id uuid NOT NULL,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz,
  reason text NOT NULL CHECK (char_length(btrim(reason)) BETWEEN 1 AND 500),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (isfinite(starts_at)),
  CHECK (ends_at IS NULL OR (isfinite(ends_at) AND ends_at > starts_at)),
  FOREIGN KEY (tenant_id, site_id, revision_id, segment_id)
    REFERENCES mining_route_segment (tenant_id, site_id, revision_id, segment_id) ON DELETE RESTRICT
);
CREATE INDEX ix_mining_route_closure_scope
  ON mining_route_closure (tenant_id, site_id, revision_id, segment_id, starts_at);
SELECT app.apply_tenant_rls('mining_route_closure', 'SELECT, INSERT');
"""

DOWNGRADE = r"""
DROP TABLE mining_route_closure;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
