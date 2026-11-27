"""Mining route graph foundation; drafts only, no routing activation.

Revision ID: 0081
Revises: 0080
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE mining_route_revision (
  revision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  version integer NOT NULL CHECK (version > 0),
  status text NOT NULL DEFAULT 'DRAFT' CHECK (status = 'DRAFT'),
  provenance text NOT NULL CHECK (char_length(btrim(provenance)) BETWEEN 1 AND 500),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, site_id, revision_id),
  UNIQUE (tenant_id, site_id, version),
  FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT
);
SELECT app.apply_tenant_rls('mining_route_revision', 'SELECT, INSERT');

CREATE TABLE mining_route_node (
  node_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  revision_id uuid NOT NULL,
  position geometry(Point,4326) NOT NULL,
  provenance text NOT NULL CHECK (char_length(btrim(provenance)) BETWEEN 1 AND 500),
  CHECK (NOT ST_IsEmpty(position) AND ST_IsValid(position)
    AND ST_X(position) BETWEEN -180 AND 180 AND ST_Y(position) BETWEEN -90 AND 90),
  UNIQUE (tenant_id, site_id, revision_id, node_id),
  FOREIGN KEY (tenant_id, site_id, revision_id)
    REFERENCES mining_route_revision (tenant_id, site_id, revision_id) ON DELETE RESTRICT
);
CREATE INDEX ix_mining_route_node_position ON mining_route_node USING gist (position);
SELECT app.apply_tenant_rls('mining_route_node', 'SELECT, INSERT');

CREATE TABLE mining_route_segment (
  segment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  revision_id uuid NOT NULL,
  origin_id uuid NOT NULL,
  destination_id uuid NOT NULL,
  path geometry(LineString,4326) NOT NULL,
  distance_m integer NOT NULL CHECK (distance_m > 0),
  duration_seconds integer NOT NULL CHECK (duration_seconds > 0),
  provenance text NOT NULL CHECK (char_length(btrim(provenance)) BETWEEN 1 AND 500),
  CHECK (origin_id <> destination_id),
  CHECK (NOT ST_IsEmpty(path) AND ST_IsValid(path) AND ST_IsSimple(path)
    AND ST_XMin(path) >= -180 AND ST_XMax(path) <= 180
    AND ST_YMin(path) >= -90 AND ST_YMax(path) <= 90),
  UNIQUE (tenant_id, site_id, revision_id, segment_id),
  FOREIGN KEY (tenant_id, site_id, revision_id, origin_id)
    REFERENCES mining_route_node (tenant_id, site_id, revision_id, node_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, site_id, revision_id, destination_id)
    REFERENCES mining_route_node (tenant_id, site_id, revision_id, node_id) ON DELETE RESTRICT
);
CREATE INDEX ix_mining_route_segment_origin
  ON mining_route_segment (tenant_id, site_id, revision_id, origin_id);
CREATE INDEX ix_mining_route_segment_destination
  ON mining_route_segment (tenant_id, site_id, revision_id, destination_id);
CREATE INDEX ix_mining_route_segment_path ON mining_route_segment USING gist (path);
SELECT app.apply_tenant_rls('mining_route_segment', 'SELECT, INSERT');

CREATE FUNCTION app.check_mining_route_segment_geometry() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER AS $mining_geometry$
DECLARE
  origin_position geometry;
  destination_position geometry;
BEGIN
  SELECT position INTO origin_position FROM mining_route_node
    WHERE tenant_id = NEW.tenant_id AND site_id = NEW.site_id
      AND revision_id = NEW.revision_id AND node_id = NEW.origin_id;
  SELECT position INTO destination_position FROM mining_route_node
    WHERE tenant_id = NEW.tenant_id AND site_id = NEW.site_id
      AND revision_id = NEW.revision_id AND node_id = NEW.destination_id;
  IF origin_position IS NULL OR destination_position IS NULL THEN
    RAISE EXCEPTION 'mining route endpoint unavailable' USING ERRCODE = '23503';
  END IF;
  IF NOT ST_Equals(ST_StartPoint(NEW.path), origin_position)
    OR NOT ST_Equals(ST_EndPoint(NEW.path), destination_position) THEN
    RAISE EXCEPTION 'mining route geometry does not match directed endpoints'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$mining_geometry$;
CREATE TRIGGER trg_mining_route_segment_geometry
  BEFORE INSERT OR UPDATE ON mining_route_segment
  FOR EACH ROW EXECUTE FUNCTION app.check_mining_route_segment_geometry();
"""

DOWNGRADE = r"""
DROP TABLE mining_route_segment;
DROP FUNCTION app.check_mining_route_segment_geometry();
DROP TABLE mining_route_node;
DROP TABLE mining_route_revision;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
