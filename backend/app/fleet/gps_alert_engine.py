"""Évaluation des alertes GPS à l'ingestion d'une position mesurée (même transaction que l'écriture).

Règles (docs/GPS_ALERTS.md) :
- seule la mesure **la plus récente** de l'engin fait évoluer les alertes : une position reçue en retard
  (antérieure à une autre déjà stockée) est conservée dans l'historique mais n'ouvre ni ne ferme rien ;
- **excès de vitesse** : vitesse mesurée strictement supérieure à la limite du site. L'alerte reste ouverte
  tant que les mesures dépassent (vitesse maximale retenue) et se ferme à la première mesure revenue au plus
  à la limite. Une mesure sans vitesse ne change rien. Sans limite pour le site : aucune alerte ;
- **perte de signal** : ouverte par le balayage planifié (gps_signal_sweep), fermée ici par la première
  position reçue ensuite ;
- **zones** : entrée dans une zone interdite active, sortie de la limite active du site, par comparaison avec
  la mesure précédente de l'engin (pas d'alerte au premier point : l'état initial est inconnu).
Le contexte RLS est celui de l'appelant (passerelle authentifiée ou session du téléphone).
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.fleet.gps_alert_models import GpsAlert, SiteGpsPolicy
from app.fleet.gps_models import FleetGpsPosition

_INSIDE = text(
    "SELECT site_geofence_id, kind FROM site_geofence "
    "WHERE tenant_id = :tenant AND site_id = :site AND active AND kind IN ('RESTRICTED', 'SITE_BOUNDARY') "
    "AND ST_Covers(area, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography)"
)


def _zones(
    db: Session, tenant_id: uuid.UUID, site_id: uuid.UUID, lat: float, lon: float
) -> dict[uuid.UUID, str]:
    rows = db.execute(_INSIDE, {"tenant": tenant_id, "site": site_id, "lat": lat, "lon": lon}).all()
    return {row.site_geofence_id: row.kind for row in rows}


def _active_zones(db: Session, tenant_id: uuid.UUID, site_id: uuid.UUID) -> dict[uuid.UUID, str]:
    rows = db.execute(
        text(
            "SELECT site_geofence_id, kind FROM site_geofence WHERE tenant_id = :tenant AND site_id = :site "
            "AND active AND kind IN ('RESTRICTED', 'SITE_BOUNDARY')"
        ),
        {"tenant": tenant_id, "site": site_id},
    ).all()
    return {row.site_geofence_id: row.kind for row in rows}


def evaluate_position_alerts(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    gps_position_id: uuid.UUID,
    recorded_at: datetime,
    latitude: float,
    longitude: float,
    speed_kmh: float | None,
) -> None:
    # Le signal revient : toute position reçue (même tardive) ferme la perte de signal ouverte, au plus tôt
    # à l'instant de détection.
    lost = db.scalar(
        select(GpsAlert)
        .where(
            GpsAlert.tenant_id == tenant_id,
            GpsAlert.vehicle_id == vehicle_id,
            GpsAlert.kind == "SIGNAL_LOST",
            GpsAlert.closed_at.is_(None),
        )
        .with_for_update()
    )
    if lost is not None:
        lost.closed_at = max(lost.opened_at, recorded_at)
    newer = db.scalar(
        select(FleetGpsPosition.gps_position_id)
        .where(
            FleetGpsPosition.tenant_id == tenant_id,
            FleetGpsPosition.vehicle_id == vehicle_id,
            FleetGpsPosition.recorded_at > recorded_at,
        )
        .limit(1)
    )
    if newer is not None:
        return  # position tardive : l'état des alertes suit la mesure la plus récente
    _overspeed(db, tenant_id, site_id, vehicle_id, recorded_at, latitude, longitude, speed_kmh)
    _zone_alerts(db, tenant_id, site_id, vehicle_id, gps_position_id, recorded_at, latitude, longitude)


def _overspeed(
    db: Session,
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    recorded_at: datetime,
    latitude: float,
    longitude: float,
    speed_kmh: float | None,
) -> None:
    if speed_kmh is None:
        return
    limit = db.scalar(
        select(SiteGpsPolicy.speed_limit_kmh).where(
            SiteGpsPolicy.tenant_id == tenant_id, SiteGpsPolicy.site_id == site_id
        )
    )
    alert = db.scalar(
        select(GpsAlert)
        .where(
            GpsAlert.tenant_id == tenant_id,
            GpsAlert.vehicle_id == vehicle_id,
            GpsAlert.kind == "OVERSPEED",
            GpsAlert.closed_at.is_(None),
        )
        .with_for_update()
    )
    over = limit is not None and Decimal(str(speed_kmh)) > limit
    if alert is not None:
        alert.last_measured_at = max(alert.last_measured_at, recorded_at)
        if over:
            alert.peak_speed_kmh = max(alert.peak_speed_kmh or 0.0, speed_kmh)
        else:
            alert.closed_at = recorded_at
        return
    if over:
        db.execute(
            insert(GpsAlert)
            .values(
                tenant_id=tenant_id,
                site_id=site_id,
                vehicle_id=vehicle_id,
                kind="OVERSPEED",
                opened_at=recorded_at,
                last_measured_at=recorded_at,
                latitude=latitude,
                longitude=longitude,
                speed_limit_kmh=limit,
                peak_speed_kmh=speed_kmh,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "vehicle_id"],
                index_where=text("kind = 'OVERSPEED' AND closed_at IS NULL"),
            )
        )


def _zone_alerts(
    db: Session,
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    gps_position_id: uuid.UUID,
    recorded_at: datetime,
    latitude: float,
    longitude: float,
) -> None:
    if not _active_zones(db, tenant_id, site_id):
        return
    previous = db.execute(
        select(FleetGpsPosition.latitude, FleetGpsPosition.longitude)
        .where(
            FleetGpsPosition.tenant_id == tenant_id,
            FleetGpsPosition.vehicle_id == vehicle_id,
            FleetGpsPosition.recorded_at < recorded_at,
            FleetGpsPosition.gps_position_id != gps_position_id,
        )
        .order_by(FleetGpsPosition.recorded_at.desc())
        .limit(1)
    ).first()
    if previous is None:
        return
    before = _zones(db, tenant_id, site_id, previous.latitude, previous.longitude)
    now = _zones(db, tenant_id, site_id, latitude, longitude)
    events: list[tuple[str, uuid.UUID]] = [
        ("RESTRICTED_ZONE_ENTRY", g) for g, kind in now.items() if kind == "RESTRICTED" and g not in before
    ]
    events += [
        ("SITE_BOUNDARY_EXIT", g) for g, kind in before.items() if kind == "SITE_BOUNDARY" and g not in now
    ]
    for kind, geofence_id in events:
        db.add(
            GpsAlert(
                tenant_id=tenant_id,
                site_id=site_id,
                vehicle_id=vehicle_id,
                kind=kind,
                opened_at=recorded_at,
                last_measured_at=recorded_at,
                closed_at=recorded_at,
                latitude=latitude,
                longitude=longitude,
                site_geofence_id=geofence_id,
            )
        )
    if events:
        db.flush()
