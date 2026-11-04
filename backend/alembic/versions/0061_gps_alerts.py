"""Alertes GPS : excès de vitesse, entrée en zone interdite, sortie de la limite du site.

Revision ID: 0061
Revises: 0060

- `site_gps_policy` : réglages d'alerte par site (vitesse limite ; sans limite, aucune alerte de vitesse).
- `gps_alert` : une alerte naît d'une position **mesurée** (la plus récente de l'engin au moment de l'ingestion) ;
  une alerte de vitesse reste ouverte tant que les mesures dépassent la limite (vitesse maximale retenue) et se
  ferme à la première mesure revenue sous la limite. Les alertes de zone sont ponctuelles. La prise en compte
  (acquittement) est tracée. Une seule alerte de vitesse ouverte par engin (index unique partiel).
Voir docs/GPS_ALERTS.md.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE site_gps_policy (
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  speed_limit_kmh numeric(5,1),
  updated_by uuid NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_site_gps_policy PRIMARY KEY (tenant_id, site_id),
  CONSTRAINT fk_sgp__site FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_sgp__author FOREIGN KEY (tenant_id, updated_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_sgp_speed CHECK (speed_limit_kmh IS NULL OR (speed_limit_kmh > 0 AND speed_limit_kmh <= 250))
);
SELECT app.apply_tenant_rls('site_gps_policy', 'SELECT, INSERT, UPDATE');

CREATE TABLE gps_alert (
  gps_alert_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  kind text NOT NULL,
  opened_at timestamptz NOT NULL,
  last_measured_at timestamptz NOT NULL,
  closed_at timestamptz,
  latitude double precision NOT NULL,
  longitude double precision NOT NULL,
  speed_limit_kmh numeric(5,1),
  peak_speed_kmh real,
  site_geofence_id uuid,
  acknowledged_by uuid,
  acknowledged_at timestamptz,
  acknowledgement_note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_gps_alert PRIMARY KEY (gps_alert_id),
  CONSTRAINT uq_gps_alert_tenant_id UNIQUE (tenant_id, gps_alert_id),
  CONSTRAINT fk_ga__site FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_ga__vehicle FOREIGN KEY (tenant_id, vehicle_id)
    REFERENCES vehicle (tenant_id, vehicle_id) ON DELETE RESTRICT,
  CONSTRAINT fk_ga__geofence FOREIGN KEY (tenant_id, site_geofence_id)
    REFERENCES site_geofence (tenant_id, site_geofence_id) ON DELETE RESTRICT,
  CONSTRAINT fk_ga__ack FOREIGN KEY (tenant_id, acknowledged_by)
    REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT ck_ga_kind CHECK (kind IN ('OVERSPEED','RESTRICTED_ZONE_ENTRY','SITE_BOUNDARY_EXIT')),
  CONSTRAINT ck_ga_detail CHECK (
    (kind = 'OVERSPEED' AND speed_limit_kmh IS NOT NULL AND peak_speed_kmh IS NOT NULL AND site_geofence_id IS NULL)
    OR (kind <> 'OVERSPEED' AND site_geofence_id IS NOT NULL AND closed_at = opened_at)
  ),
  CONSTRAINT ck_ga_times CHECK (last_measured_at >= opened_at AND (closed_at IS NULL OR closed_at >= opened_at)),
  CONSTRAINT ck_ga_position CHECK (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180),
  CONSTRAINT ck_ga_ack CHECK ((acknowledged_by IS NULL) = (acknowledged_at IS NULL)),
  CONSTRAINT ck_ga_note CHECK (acknowledgement_note IS NULL OR char_length(acknowledgement_note) <= 500)
);
CREATE UNIQUE INDEX uq_ga_open_overspeed ON gps_alert (tenant_id, vehicle_id)
  WHERE kind = 'OVERSPEED' AND closed_at IS NULL;
CREATE INDEX ix_ga_site_time ON gps_alert (tenant_id, site_id, opened_at DESC);
CREATE INDEX ix_ga_unacknowledged ON gps_alert (tenant_id, site_id) WHERE acknowledged_at IS NULL;
SELECT app.apply_tenant_rls('gps_alert', 'SELECT, INSERT, UPDATE');
"""

DOWNGRADE = r"""
DROP TABLE gps_alert;
DROP TABLE site_gps_policy;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
