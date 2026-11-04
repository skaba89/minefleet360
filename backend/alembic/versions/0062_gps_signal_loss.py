"""Alerte de perte de signal GPS (balayage planifié) ; délai réglable par site.

Revision ID: 0062
Revises: 0061

- `site_gps_policy.signal_loss_minutes` : délai sans mesure au-delà duquel un engin disponible équipé d'un traceur
  actif est signalé (5 à 1 440 min ; vide = pas de surveillance, valeur par défaut).
- `gps_alert.kind` accepte `SIGNAL_LOST` : ouverte par la commande planifiée `minefleet sweep-gps-signal`, fermée
  par la première position reçue ensuite (à l'ingestion). Une seule ouverte par engin (index unique partiel).
Voir docs/GPS_ALERTS.md.
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE site_gps_policy
  ADD COLUMN signal_loss_minutes integer,
  ADD CONSTRAINT ck_sgp_signal_loss CHECK (signal_loss_minutes IS NULL OR signal_loss_minutes BETWEEN 5 AND 1440);
ALTER TABLE gps_alert DROP CONSTRAINT ck_ga_kind;
ALTER TABLE gps_alert ADD CONSTRAINT ck_ga_kind
  CHECK (kind IN ('OVERSPEED','RESTRICTED_ZONE_ENTRY','SITE_BOUNDARY_EXIT','SIGNAL_LOST'));
ALTER TABLE gps_alert DROP CONSTRAINT ck_ga_detail;
ALTER TABLE gps_alert ADD CONSTRAINT ck_ga_detail CHECK (
  (kind = 'OVERSPEED' AND speed_limit_kmh IS NOT NULL AND peak_speed_kmh IS NOT NULL AND site_geofence_id IS NULL)
  OR (kind IN ('RESTRICTED_ZONE_ENTRY','SITE_BOUNDARY_EXIT') AND site_geofence_id IS NOT NULL AND closed_at = opened_at)
  OR (kind = 'SIGNAL_LOST' AND site_geofence_id IS NULL AND speed_limit_kmh IS NULL AND peak_speed_kmh IS NULL)
);
ALTER TABLE gps_alert DROP CONSTRAINT ck_ga_times;
-- Perte de signal : ouverte à la détection, après la dernière mesure (last_measured_at <= opened_at).
ALTER TABLE gps_alert ADD CONSTRAINT ck_ga_times CHECK (
  (closed_at IS NULL OR closed_at >= opened_at)
  AND (CASE WHEN kind = 'SIGNAL_LOST' THEN last_measured_at <= opened_at ELSE last_measured_at >= opened_at END)
);
CREATE UNIQUE INDEX uq_ga_open_signal_lost ON gps_alert (tenant_id, vehicle_id)
  WHERE kind = 'SIGNAL_LOST' AND closed_at IS NULL;
"""

DOWNGRADE = r"""
-- Retour arrière destructif (garde guard_destructive) : les alertes de perte de signal disparaissent.
ALTER TABLE gps_alert NO FORCE ROW LEVEL SECURITY;
DELETE FROM gps_alert WHERE kind = 'SIGNAL_LOST';
ALTER TABLE gps_alert FORCE ROW LEVEL SECURITY;
DROP INDEX uq_ga_open_signal_lost;
ALTER TABLE gps_alert DROP CONSTRAINT ck_ga_times;
ALTER TABLE gps_alert ADD CONSTRAINT ck_ga_times
  CHECK (last_measured_at >= opened_at AND (closed_at IS NULL OR closed_at >= opened_at));
ALTER TABLE gps_alert DROP CONSTRAINT ck_ga_detail;
ALTER TABLE gps_alert ADD CONSTRAINT ck_ga_detail CHECK (
  (kind = 'OVERSPEED' AND speed_limit_kmh IS NOT NULL AND peak_speed_kmh IS NOT NULL AND site_geofence_id IS NULL)
  OR (kind <> 'OVERSPEED' AND site_geofence_id IS NOT NULL AND closed_at = opened_at)
);
ALTER TABLE gps_alert DROP CONSTRAINT ck_ga_kind;
ALTER TABLE gps_alert ADD CONSTRAINT ck_ga_kind CHECK (kind IN ('OVERSPEED','RESTRICTED_ZONE_ENTRY','SITE_BOUNDARY_EXIT'));
ALTER TABLE site_gps_policy DROP CONSTRAINT ck_sgp_signal_loss, DROP COLUMN signal_loss_minutes;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
