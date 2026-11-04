"""Balayage planifié de la perte de signal GPS (commande `minefleet sweep-gps-signal`, acteur SYSTEM).

Règle (docs/GPS_ALERTS.md) : un engin **disponible**, équipé d'un **traceur actif**, sur un site dont le
délai `signal_loss_minutes` est réglé, dont la dernière position mesurée date de plus que ce délai, reçoit
une alerte `SIGNAL_LOST` (au plus une ouverte par engin). Les engins en maintenance, immobilisés ou hors
service, qui peuvent être légitimement éteints, ne sont pas surveillés ; un engin qui n'a jamais émis non
plus (rien à localiser). L'alerte se ferme à l'ingestion de la position suivante (gps_alert_engine).
Le contexte société (RLS) est posé par l'appelant.
"""

import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit.contracts import record
from app.fleet.gps_alert_notify import enqueue_alert_notifications

_SWEEP = text(
    """
    INSERT INTO gps_alert
      (tenant_id, site_id, vehicle_id, kind, opened_at, last_measured_at, latitude, longitude)
    SELECT v.tenant_id, v.site_id, v.vehicle_id, 'SIGNAL_LOST', :now,
           last.recorded_at, last.latitude, last.longitude
    FROM site_gps_policy pol
    JOIN vehicle v ON v.tenant_id = pol.tenant_id AND v.site_id = pol.site_id AND v.status = 'AVAILABLE'
    JOIN LATERAL (
      SELECT 1 FROM fleet_gps_device_binding b
      WHERE b.tenant_id = v.tenant_id AND b.vehicle_id = v.vehicle_id
        AND b.revoked_at IS NULL AND b.active_from <= :now
      LIMIT 1
    ) tracker ON true
    JOIN LATERAL (
      SELECT p.recorded_at, p.latitude, p.longitude FROM fleet_gps_position p
      WHERE p.tenant_id = v.tenant_id AND p.vehicle_id = v.vehicle_id
      ORDER BY p.recorded_at DESC LIMIT 1
    ) last ON true
    WHERE pol.tenant_id = :tenant AND pol.signal_loss_minutes IS NOT NULL
      AND last.recorded_at < CAST(:now AS timestamptz) - make_interval(mins => pol.signal_loss_minutes)
    ON CONFLICT (tenant_id, vehicle_id) WHERE kind = 'SIGNAL_LOST' AND closed_at IS NULL DO NOTHING
    RETURNING gps_alert_id, site_id, vehicle_id
    """
)


def sweep_tenant_signal_loss(db: Session, tenant_id: uuid.UUID, now: datetime) -> int:
    rows = db.execute(_SWEEP, {"tenant": tenant_id, "now": now}).all()
    for row in rows:
        enqueue_alert_notifications(
            db,
            tenant_id=tenant_id,
            gps_alert_id=row.gps_alert_id,
            site_id=row.site_id,
            vehicle_id=row.vehicle_id,
            kind="SIGNAL_LOST",
        )
    opened = len(rows)
    if opened:
        record(
            db,
            tenant_id=tenant_id,
            actor_kind="SYSTEM",
            action="fleet.gps.signal_loss.sweep",
            entity_type="gps_alert",
            after={"opened": opened},
        )
    return opened
