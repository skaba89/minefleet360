"""Draft technical profiles, not actual mass or operational approval.

Revision ID: 0088
Revises: 0087
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE mining_vehicle_profile (
  profile_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  vehicle_id uuid NOT NULL REFERENCES vehicle (vehicle_id) ON DELETE RESTRICT,
  version integer NOT NULL CHECK (version > 0),
  tare_mass_kg integer NOT NULL CHECK (tare_mass_kg > 0),
  max_gross_mass_kg integer NOT NULL CHECK (max_gross_mass_kg >= tare_mass_kg),
  height_mm integer NOT NULL CHECK (height_mm > 0),
  width_mm integer NOT NULL CHECK (width_mm > 0),
  length_mm integer NOT NULL CHECK (length_mm > 0),
  max_uphill_permille integer NOT NULL CHECK (max_uphill_permille >= 0),
  max_downhill_permille integer NOT NULL CHECK (max_downhill_permille >= 0),
  max_speed_kmh integer NOT NULL CHECK (max_speed_kmh > 0),
  provenance text NOT NULL CHECK (char_length(btrim(provenance)) BETWEEN 1 AND 500),
  status text NOT NULL DEFAULT 'DRAFT' CHECK (status = 'DRAFT'),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, vehicle_id, version)
);
SELECT app.apply_tenant_rls('mining_vehicle_profile', 'SELECT, INSERT');

CREATE FUNCTION app.check_mining_vehicle_profile_scope() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER AS $vehicle_profile$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM vehicle WHERE vehicle_id = NEW.vehicle_id AND tenant_id = NEW.tenant_id
  ) THEN
    RAISE EXCEPTION 'vehicle unavailable in tenant' USING ERRCODE = '23503';
  END IF;
  RETURN NEW;
END;
$vehicle_profile$;
CREATE TRIGGER trg_mining_vehicle_profile_scope
  BEFORE INSERT ON mining_vehicle_profile
  FOR EACH ROW EXECUTE FUNCTION app.check_mining_vehicle_profile_scope();
COMMENT ON COLUMN mining_vehicle_profile.max_gross_mass_kg IS
  'Technical ceiling only; never a measured gross mass';
"""

DOWNGRADE = r"""
DROP TABLE mining_vehicle_profile;
DROP FUNCTION app.check_mining_vehicle_profile_scope();
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
