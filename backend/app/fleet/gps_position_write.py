"""Écriture GPS interne et idempotente, après validation d'une passerelle fiable.

Le contexte tenant/site est fourni par la passerelle authentifiée. Une
position répétée est ignorée grâce à la contrainte SQL unique existante.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.fleet.gps_alert_engine import evaluate_position_alerts
from app.fleet.gps_contract import GpsPosition
from app.fleet.gps_ingestion_preflight import preflight_gps_ingestion
from app.fleet.gps_models import FleetGpsPosition


def _drapeaux_qualite(position: GpsPosition, received_at: datetime) -> tuple[bool, bool]:
    """§1.3 : drapeaux `late` et `clock_skew_suspect` au-delà des seuils configurables.

    Les deux horodatages restent stockés tels quels, jamais corrigés ; le
    drapeau capture l'évaluation faite à l'ingestion, pas une correction.
    """
    settings = get_settings()
    ecart = received_at.astimezone(UTC) - position.recorded_at.astimezone(UTC)
    late = ecart > timedelta(seconds=settings.gps_late_threshold_seconds)
    skew = abs(ecart.total_seconds()) > settings.gps_clock_skew_tolerance_seconds
    return late, skew


def persist_validated_gps_position(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    position: GpsPosition,
    supplied_secret: str,
    received_at: datetime,
) -> bool:
    """Renvoyer True si insérée ; False si refusée ou déjà présente.

    La transaction est gérée par l'appelant. Ce module ne doit jamais être
    exposé à un traceur sans identité de passerelle vérifiée et anti-rejeu.
    """
    if not preflight_gps_ingestion(
        db,
        tenant_id=tenant_id,
        site_id=site_id,
        position=position,
        supplied_secret=supplied_secret,
        received_at=received_at,
    ):
        return False

    late, skew = _drapeaux_qualite(position, received_at)
    statement = (
        insert(FleetGpsPosition)
        .values(
            tenant_id=tenant_id,
            vehicle_id=position.vehicle_id,
            site_id=site_id,
            device_id=position.device_id,
            latitude=position.latitude,
            longitude=position.longitude,
            speed_kmh=position.speed_kmh,
            accuracy_m=position.accuracy_m,
            heading_deg=position.heading_deg,
            recorded_at=position.recorded_at,
            received_at=received_at,
            late=late,
            clock_skew_suspect=skew,
        )
        .on_conflict_do_nothing(constraint="uq_fgp_device_time")
        .returning(FleetGpsPosition.gps_position_id)
    )
    inserted = db.execute(statement).scalar_one_or_none()
    if inserted is None:
        return False
    # Alertes (vitesse, zones) dans la même transaction que la position : rien d'orphelin en cas d'échec.
    evaluate_position_alerts(
        db,
        tenant_id=tenant_id,
        site_id=site_id,
        vehicle_id=position.vehicle_id,
        gps_position_id=inserted,
        recorded_at=position.recorded_at,
        latitude=position.latitude,
        longitude=position.longitude,
        speed_kmh=position.speed_kmh,
    )
    return True
