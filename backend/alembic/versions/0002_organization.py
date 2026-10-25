"""Organisation : site (MODELE_PHYSIQUE_LOT1 §5.2).

Revision ID: 0002
Revises: 0001
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE site (
  site_id   uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  code      text NOT NULL,
  name      text NOT NULL,
  site_type text NOT NULL,
  timezone  text,
  location  geography(Point, 4326),
  status    text NOT NULL DEFAULT 'ACTIVE',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid,
  updated_by uuid,
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_site PRIMARY KEY (site_id),
  CONSTRAINT fk_site__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT uq_site_tenant_site UNIQUE (tenant_id, site_id),
  CONSTRAINT uq_site_tenant_code UNIQUE (tenant_id, code),
  CONSTRAINT ck_site_code   CHECK (code ~ '^[A-Za-z0-9_-]{1,32}$'),
  CONSTRAINT ck_site_type   CHECK (site_type IN ('MINE','QUARRY','WORKSHOP','DEPOT','PORT','OFFICE')),
  CONSTRAINT ck_site_status CHECK (status IN ('ACTIVE','INACTIVE')),
  CONSTRAINT ck_site_tz     CHECK (timezone IS NULL OR timezone ~ '^[A-Za-z_]+(/[A-Za-z0-9_+-]+)*$'),
  CONSTRAINT ck_site_loc    CHECK (location IS NULL OR NOT (ST_X(location::geometry) = 0 AND ST_Y(location::geometry) = 0)),
  CONSTRAINT ck_site_version CHECK (row_version >= 1)
);
SELECT app.apply_tenant_rls('site', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('site');
"""

DOWNGRADE = "DROP TABLE site;"


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
