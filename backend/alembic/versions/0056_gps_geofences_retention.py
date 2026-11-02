"""GPS avancé (chantier E) : géofences de site et purge de rétention des positions.

Revision ID: 0056
Revises: 0055

Voir docs/LIVRAISON_GPS_AVANCE.md.
- `site_geofence` : polygone PostGIS (geography, WGS 84) valide, rattaché à un site, désactivable (jamais supprimé).
- Rétention : les positions restent en ajout seul pour l'application ; seule la fonction `app.purge_gps_positions`
  (SECURITY DEFINER, propriétaire, non exécutable par le rôle applicatif) supprime les positions plus anciennes
  que la date limite, en levant le garde d'ajout seul pour sa seule transaction.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE site_geofence (
  site_geofence_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  code text NOT NULL,
  name text NOT NULL,
  kind text NOT NULL,
  area geography(Polygon, 4326) NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_site_geofence PRIMARY KEY (site_geofence_id),
  CONSTRAINT uq_sgf_tenant_id UNIQUE (tenant_id, site_geofence_id),
  CONSTRAINT fk_sgf__site FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_sgf__author FOREIGN KEY (tenant_id, created_by) REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_sgf_code CHECK (code ~ '^[A-Za-z0-9_-]{1,48}$'),
  CONSTRAINT ck_sgf_name CHECK (char_length(name) BETWEEN 2 AND 120),
  CONSTRAINT ck_sgf_kind CHECK (kind IN ('SITE_BOUNDARY','LOADING_AREA','DUMP_AREA','WORKSHOP','FUEL_STATION',
                                         'RESTRICTED','OTHER')),
  CONSTRAINT ck_sgf_valid CHECK (ST_IsValid(area::geometry)),
  -- Bornes de vraisemblance : de 100 m² à 2 000 km² (une concession minière entière).
  CONSTRAINT ck_sgf_area CHECK (ST_Area(area) BETWEEN 100 AND 2000000000),
  CONSTRAINT ck_sgf_version CHECK (row_version >= 1)
);
CREATE UNIQUE INDEX uq_sgf_site_code ON site_geofence (tenant_id, site_id, lower(code));
CREATE INDEX ix_sgf_area ON site_geofence USING gist (area);
SELECT app.apply_tenant_rls('site_geofence', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('site_geofence');

-- Purge de rétention : seul chemin de suppression des positions GPS.
CREATE FUNCTION app.tg_gps_position_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' AND current_setting('app.gps_retention_purge', true) = 'on' THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION '% is append-only (% refused)', TG_TABLE_NAME, TG_OP USING ERRCODE = 'MF001';
END $$;
DROP TRIGGER tg_fleet_gps_position_append_only ON fleet_gps_position;
CREATE TRIGGER tg_fleet_gps_position_append_only BEFORE UPDATE OR DELETE ON fleet_gps_position
  FOR EACH ROW EXECUTE FUNCTION app.tg_gps_position_append_only();

CREATE FUNCTION app.purge_gps_positions(p_cutoff timestamptz, p_dry_run boolean DEFAULT true)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE n bigint;
BEGIN
  IF p_cutoff > now() - interval '7 days' THEN
    RAISE EXCEPTION 'date limite trop récente : 7 jours d''historique minimum' USING ERRCODE = 'MF002';
  END IF;
  -- Le propriétaire n'est pas soumis à la RLS forcée ici : la purge porte sur tous les tenants (rétention globale).
  EXECUTE 'ALTER TABLE public.fleet_gps_position NO FORCE ROW LEVEL SECURITY';
  IF p_dry_run THEN
    SELECT count(*) INTO n FROM public.fleet_gps_position WHERE recorded_at < p_cutoff;
  ELSE
    PERFORM set_config('app.gps_retention_purge', 'on', true);
    DELETE FROM public.fleet_gps_position WHERE recorded_at < p_cutoff;
    GET DIAGNOSTICS n = ROW_COUNT;
    PERFORM set_config('app.gps_retention_purge', 'off', true);
  END IF;
  EXECUTE 'ALTER TABLE public.fleet_gps_position FORCE ROW LEVEL SECURITY';
  RETURN n;
END $$;
REVOKE ALL ON FUNCTION app.purge_gps_positions(timestamptz, boolean) FROM PUBLIC;
"""

DOWNGRADE = r"""
DROP FUNCTION app.purge_gps_positions(timestamptz, boolean);
DROP TRIGGER tg_fleet_gps_position_append_only ON fleet_gps_position;
CREATE TRIGGER tg_fleet_gps_position_append_only BEFORE UPDATE OR DELETE ON fleet_gps_position
  FOR EACH ROW EXECUTE FUNCTION app.tg_append_only();
DROP FUNCTION app.tg_gps_position_append_only();
DROP TABLE site_geofence;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
