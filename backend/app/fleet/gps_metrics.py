"""Métriques de qualité du suivi GPS (SLO) : agrégats mesurés, aucune position exposée.

Complète le banc synthétique (`docs/qa/GPS_PERFORMANCE_EVIDENCE.md`, workflow `gps-benchmark-tests`)
par la mesure telle que vécue par la plateforme, sur une fenêtre bornée :

- **latence d'ingestion** (`received_at` − `recorded_at`) : p50/p95/p99/max et nombre de messages à
  horloge de boîtier en avance — latence négative possible dans la borne du contrat GPS
  (`gps_contract.valid_gps_position` : 2 minutes de futur tolérées) ;
- **fraîcheur** : âge (plancher 0 : une position datée du futur est reçue maintenant) de la dernière
  position connue par engin (p50/p95/max) et nombre d'engins obsolètes au seuil `STALE` du module
  GPS avancé (30 min).

Principes :
- **agrégats uniquement** : aucune position, rien de rattachable à un conducteur — pas de finalité
  T-31 ni d'audit par consultation ; la portée reste celle de `fleet.gps.history` (tenant ou site) ;
- fenêtre bornée à 24 h (`minutes` = 1..1440) ; aucune interpolation : un trou de réception reste un trou ;
- l'endpoint fournit la **mesure**, pas un verdict : les cibles SLO seront figées lors de l'éprouvetage
  staging (`docs/ops/RECETTE_STAGING_VALIDATION.md`, condition GO n°7) — aucun seuil inventé ici.
"""

import uuid
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.fleet.gps_history import STALE

router = APIRouter(tags=["géolocalisation"], route_class=SecuredRoute)
Metrics = Annotated[Authorized, Depends(Require("fleet.gps.history"))]

MAX_WINDOW_MINUTES = 1440

_LATENCY_SQL = text(
    """
    SELECT count(*)                                            AS n,
           percentile_cont(ARRAY[0.5, 0.95, 0.99]) WITHIN GROUP (
               ORDER BY EXTRACT(EPOCH FROM (received_at - recorded_at))
           )                                                   AS pct,
           max(EXTRACT(EPOCH FROM (received_at - recorded_at))) AS worst,
           count(*) FILTER (WHERE received_at < recorded_at)   AS skew
    FROM fleet_gps_position
    WHERE tenant_id = :tenant
      AND ((:site_ids)::uuid[] IS NULL OR site_id = ANY((:site_ids)::uuid[]))
      AND recorded_at >= :start
      AND recorded_at < :end
    """
)

_FRESHNESS_SQL = text(
    """
    SELECT count(*)                                             AS n,
           percentile_cont(ARRAY[0.5, 0.95]) WITHIN GROUP (
               ORDER BY GREATEST(0, EXTRACT(EPOCH FROM (:now - latest)))
           )                                                    AS pct,
           max(GREATEST(0, EXTRACT(EPOCH FROM (:now - latest)))) AS worst,
           count(*) FILTER (WHERE :now - latest > :stale)       AS stale
    FROM (
        SELECT max(recorded_at) AS latest
        FROM fleet_gps_position
        WHERE tenant_id = :tenant
          AND ((:site_ids)::uuid[] IS NULL OR site_id = ANY((:site_ids)::uuid[]))
        GROUP BY vehicle_id
    ) per_vehicle
    """
)


class IngestionLatency(BaseModel):
    """Latence d'ingestion en secondes ; `None` quand la fenêtre ne contient aucune position."""

    p50_s: float | None
    p95_s: float | None
    p99_s: float | None
    max_s: float | None
    negative_skew_count: int


class Freshness(BaseModel):
    """Âge de la dernière position connue par engin, en secondes."""

    vehicles_reporting: int
    p50_age_s: float | None
    p95_age_s: float | None
    max_age_s: float | None
    stale_count: int


class GpsMetricsOut(BaseModel):
    window_minutes: int
    positions_count: int
    generated_at: datetime
    ingestion_latency: IngestionLatency
    freshness: Freshness


def _site_filter(auth: Authorized) -> tuple[uuid.UUID, list[uuid.UUID] | None]:
    """Filtre SQL de portée : tenant entier, ou sites explicites d'une portée SITE."""
    if auth.scope.tenant_wide:
        return auth.tenant_id, None
    return auth.tenant_id, sorted(auth.scope.site_ids)


def gps_quality_metrics(auth: Authorized, minutes: int) -> GpsMetricsOut:
    """Agrégats de qualité du suivi GPS sur la fenêtre, dans la portée de l'appelant."""
    if not 1 <= minutes <= MAX_WINDOW_MINUTES:
        raise ValueError("minutes")
    end = auth.clock.now()
    start = end - timedelta(minutes=minutes)
    tenant, site_ids = _site_filter(auth)

    latency = (
        auth.db.execute(
            _LATENCY_SQL,
            {"tenant": tenant, "site_ids": site_ids, "start": start, "end": end},
        )
        .mappings()
        .one()
    )
    freshness = (
        auth.db.execute(
            _FRESHNESS_SQL,
            {"tenant": tenant, "site_ids": site_ids, "now": end, "stale": STALE},
        )
        .mappings()
        .one()
    )

    count = int(latency["n"])
    percentiles = list(latency["pct"]) if count else [None, None, None]
    ages = list(freshness["pct"]) if int(freshness["n"]) else [None, None]
    return GpsMetricsOut(
        window_minutes=minutes,
        positions_count=count,
        generated_at=end,
        ingestion_latency=IngestionLatency(
            p50_s=round(percentiles[0], 1) if percentiles[0] is not None else None,
            p95_s=round(percentiles[1], 1) if percentiles[1] is not None else None,
            p99_s=round(percentiles[2], 1) if percentiles[2] is not None else None,
            max_s=round(float(latency["worst"]), 1) if count else None,
            negative_skew_count=int(latency["skew"]),
        ),
        freshness=Freshness(
            vehicles_reporting=int(freshness["n"]),
            p50_age_s=round(ages[0], 1) if ages[0] is not None else None,
            p95_age_s=round(ages[1], 1) if ages[1] is not None else None,
            max_age_s=round(float(freshness["worst"]), 1) if int(freshness["n"]) else None,
            stale_count=int(freshness["stale"]),
        ),
    )


@router.get("/gps/metrics", response_model=GpsMetricsOut)
def gps_metrics(
    auth: Metrics,
    minutes: Annotated[int, Query(ge=1, le=MAX_WINDOW_MINUTES)] = 60,
) -> GpsMetricsOut:
    """Qualité du suivi GPS (latence d'ingestion, fraîcheur) sur la fenêtre, portée de l'appelant."""
    return gps_quality_metrics(auth, minutes)
