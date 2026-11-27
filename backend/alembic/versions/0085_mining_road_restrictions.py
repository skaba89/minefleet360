"""Draft road restrictions and explicit category allowlist.

Revision ID: 0085
Revises: 0084
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE mining_road_restriction (
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  revision_id uuid NOT NULL,
  segment_id uuid NOT NULL,
  max_gross_mass_kg integer NOT NULL CHECK (max_gross_mass_kg > 0),
  max_speed_kmh integer NOT NULL CHECK (max_speed_kmh > 0),
  provenance text NOT NULL CHECK (char_length(btrim(provenance)) BETWEEN 1 AND 500),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, site_id, revision_id, segment_id),
  FOREIGN KEY (tenant_id, site_id, revision_id, segment_id)
    REFERENCES mining_route_segment (tenant_id, site_id, revision_id, segment_id) ON DELETE RESTRICT
);
SELECT app.apply_tenant_rls('mining_road_restriction', 'SELECT, INSERT');

CREATE TABLE mining_road_allowed_category (
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  revision_id uuid NOT NULL,
  segment_id uuid NOT NULL,
  vehicle_category_id uuid NOT NULL,
  PRIMARY KEY (tenant_id, site_id, revision_id, segment_id, vehicle_category_id),
  FOREIGN KEY (tenant_id, site_id, revision_id, segment_id)
    REFERENCES mining_road_restriction (tenant_id, site_id, revision_id, segment_id) ON DELETE RESTRICT,
  FOREIGN KEY (vehicle_category_id)
    REFERENCES vehicle_category (vehicle_category_id) ON DELETE RESTRICT
);
SELECT app.apply_tenant_rls('mining_road_allowed_category', 'SELECT, INSERT');

CREATE FUNCTION app.check_mining_road_category_scope() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER AS $road_category$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM vehicle_category
    WHERE tenant_id = NEW.tenant_id AND vehicle_category_id = NEW.vehicle_category_id
  ) THEN
    RAISE EXCEPTION 'vehicle category unavailable in tenant' USING ERRCODE = '23503';
  END IF;
  RETURN NEW;
END;
$road_category$;
CREATE TRIGGER trg_mining_road_category_scope
  BEFORE INSERT ON mining_road_allowed_category
  FOR EACH ROW EXECUTE FUNCTION app.check_mining_road_category_scope();
"""

DOWNGRADE = r"""
DROP TABLE mining_road_allowed_category;
DROP FUNCTION app.check_mining_road_category_scope();
DROP TABLE mining_road_restriction;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
