"""GPS avancé : géofences, trajets, entrées/sorties de zones, immobilisations.

Voir docs/LIVRAISON_GPS_AVANCE.md.

Principes :
- L'historique de positions est une donnée sensible (rattachable à un conducteur) : lecture réservée,
  **finalité obligatoire** et chaque consultation est tracée dans le journal d'audit (MATRICE_RBAC, T-31).
- Fenêtre bornée (24 h) et nombre de points borné ; aucune interpolation : un trou de réception reste un trou.
- Les positions imprécises (> 100 m) ou physiquement incohérentes (saut > 150 km/h) ne comptent ni dans
  la distance ni dans les transitions de zone (pas d'alerte fantôme).
- Un message reçu en retard est replacé à son heure d'enregistrement et signalé comme tardif.
- La géolocalisation d'un navigateur ne garantit pas un suivi continu en arrière-plan : trous exposés.
"""

import json
import math
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import AwareDatetime, BaseModel, Field, field_validator
from sqlalchemy import select, text

from app.audit.contracts import record
from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.errors import AppError
from app.core.http import StrictModel
from app.fleet.contracts import vehicle_facts
from app.fleet.gps_models import FleetGpsPosition
from app.organization.contracts import active_site_in_scope

router = APIRouter(tags=["géolocalisation"], route_class=SecuredRoute)
GeofenceRead = Annotated[Authorized, Depends(Require("fleet.geofence.read"))]
GeofenceManage = Annotated[Authorized, Depends(Require("fleet.geofence.manage"))]
History = Annotated[Authorized, Depends(Require("fleet.gps.history"))]

Purpose = Literal[
    "OPERATIONS_REVIEW", "INCIDENT_INVESTIGATION", "MAINTENANCE_DIAGNOSIS", "SECURITY", "CLIENT_DISPUTE"
]
GeofenceKind = Literal[
    "SITE_BOUNDARY", "LOADING_AREA", "DUMP_AREA", "WORKSHOP", "FUEL_STATION", "RESTRICTED", "OTHER"
]
MAX_WINDOW = timedelta(hours=24)
MAX_TRACK_POINTS = 5000
MAX_FEED_POSITIONS = 50_000
GAP = timedelta(minutes=10)
LATE = timedelta(minutes=5)
STOP_RADIUS_M = 50.0
STOP_MIN = timedelta(minutes=15)
MAX_ACCURACY_M = 100.0
MAX_SPEED_KMH = 150.0
FRESH = timedelta(minutes=2)
STALE = timedelta(minutes=30)


# --- Schémas -------------------------------------------------------------------------------------------


class GeofenceCreate(StrictModel):
    site_id: uuid.UUID
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,48}$")
    name: str = Field(min_length=2, max_length=120)
    kind: GeofenceKind
    # Ordre GeoJSON : [longitude, latitude], anneau fermé automatiquement.
    coordinates: list[tuple[float, float]] = Field(min_length=3, max_length=500)

    @field_validator("coordinates")
    @classmethod
    def _valid_points(cls, value: list[tuple[float, float]]) -> list[tuple[float, float]]:
        for lon, lat in value:
            if not (-180 <= lon <= 180 and -90 <= lat <= 90) or not (
                math.isfinite(lon) and math.isfinite(lat)
            ):
                raise ValueError("coordonnée hors limites")
        if len({(round(lon, 7), round(lat, 7)) for lon, lat in value}) < 3:
            raise ValueError("au moins trois sommets distincts")
        return value


class GeofenceOut(BaseModel):
    site_geofence_id: uuid.UUID
    site_id: uuid.UUID
    code: str
    name: str
    kind: GeofenceKind
    active: bool
    area_m2: float
    coordinates: list[tuple[float, float]]


class TrackPoint(BaseModel):
    latitude: float
    longitude: float
    speed_kmh: float | None
    accuracy_m: float | None
    recorded_at: datetime
    received_at: datetime
    late: bool
    source: str


class Stop(BaseModel):
    start: datetime
    end: datetime
    minutes: int
    latitude: float
    longitude: float


class Gap(BaseModel):
    start: datetime
    end: datetime
    minutes: int


class GeofenceEvent(BaseModel):
    vehicle_id: uuid.UUID
    vehicle_fleet_number: str | None
    site_geofence_id: uuid.UUID
    geofence_name: str
    geofence_kind: GeofenceKind
    event_type: Literal["ENTER", "EXIT"]
    occurred_at: datetime


class TrackOut(BaseModel):
    vehicle_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    signal: Literal["FRESH", "STALE", "LOST", "NONE"]
    last_recorded_at: datetime | None
    points: list[TrackPoint]
    truncated: bool
    distance_km: float
    gaps: list[Gap]
    stops: list[Stop]
    late_points: int
    ignored_points: int
    geofence_events: list[GeofenceEvent]


# --- Calculs purs --------------------------------------------------------------------------------------


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _precise(p: Any) -> bool:
    return p.accuracy_m is None or p.accuracy_m <= MAX_ACCURACY_M


def usable(points: list[Any]) -> list[Any]:
    """Points précis et cohérents : un saut à plus de 150 km/h depuis le dernier point retenu est écarté."""
    kept: list[Any] = []
    for p in points:
        if not _precise(p):
            continue
        if kept:
            prev = kept[-1]
            seconds = (p.recorded_at - prev.recorded_at).total_seconds()
            meters = haversine_m(prev.latitude, prev.longitude, p.latitude, p.longitude)
            # Même horodatage (doublon) ou vitesse implicite impossible : saut GPS écarté.
            if seconds <= 0 or meters / seconds * 3.6 > MAX_SPEED_KMH:
                continue
        kept.append(p)
    return kept


def distance_km(points: list[Any]) -> float:
    total = 0.0
    for a, b in pairwise(points):
        if b.recorded_at - a.recorded_at <= GAP:
            total += haversine_m(a.latitude, a.longitude, b.latitude, b.longitude)
    return round(total / 1000, 3)


def gaps(points: list[Any]) -> list[Gap]:
    return [
        Gap(
            start=a.recorded_at,
            end=b.recorded_at,
            minutes=int((b.recorded_at - a.recorded_at).total_seconds() // 60),
        )
        for a, b in pairwise(points)
        if b.recorded_at - a.recorded_at > GAP
    ]


def stops(points: list[Any]) -> list[Stop]:
    """Immobilisation : points successifs restés à moins de 50 m de l'ancre pendant au moins 15 minutes."""
    found: list[Stop] = []
    i = 0
    while i < len(points):
        anchor = points[i]
        j = i
        while (
            j + 1 < len(points)
            and haversine_m(
                anchor.latitude, anchor.longitude, points[j + 1].latitude, points[j + 1].longitude
            )
            <= STOP_RADIUS_M
            and points[j + 1].recorded_at - points[j].recorded_at <= GAP
        ):
            j += 1
        duration = points[j].recorded_at - anchor.recorded_at
        if duration >= STOP_MIN:
            found.append(
                Stop(
                    start=anchor.recorded_at,
                    end=points[j].recorded_at,
                    minutes=int(duration.total_seconds() // 60),
                    latitude=anchor.latitude,
                    longitude=anchor.longitude,
                )
            )
            i = j + 1
        else:
            i += 1
    return found


def transitions(
    ordered: list[Any], inside: dict[uuid.UUID, set[uuid.UUID]], geofence_ids: set[uuid.UUID]
) -> list[tuple[uuid.UUID, Literal["ENTER", "EXIT"], datetime]]:
    """Transitions d'appartenance zone par zone ; le premier point fixe l'état initial (pas d'événement)."""
    events: list[tuple[uuid.UUID, Literal["ENTER", "EXIT"], datetime]] = []
    previous: set[uuid.UUID] | None = None
    for p in ordered:
        current = inside.get(p.gps_position_id, set()) & geofence_ids
        if previous is not None:
            events.extend((g, "ENTER", p.recorded_at) for g in sorted(current - previous))
            events.extend((g, "EXIT", p.recorded_at) for g in sorted(previous - current))
        previous = current
    return events


def signal(last: datetime | None, now: datetime) -> Literal["FRESH", "STALE", "LOST", "NONE"]:
    if last is None:
        return "NONE"
    age = now - last
    return "FRESH" if age <= FRESH else "STALE" if age <= STALE else "LOST"


# --- Géofences -----------------------------------------------------------------------------------------


_GEOFENCE_SELECT = """
SELECT site_geofence_id, site_id, code, name, kind, active, ST_Area(area) AS area_m2,
       ST_AsGeoJSON(area::geometry) AS geojson
FROM site_geofence
"""


def _geofence_out(row: Any) -> GeofenceOut:
    ring = json.loads(row.geojson)["coordinates"][0]
    return GeofenceOut(
        site_geofence_id=row.site_geofence_id,
        site_id=row.site_id,
        code=row.code,
        name=row.name,
        kind=row.kind,
        active=row.active,
        area_m2=round(float(row.area_m2), 1),
        coordinates=[(float(c[0]), float(c[1])) for c in ring],
    )


@router.get("/geofences", response_model=list[GeofenceOut])
def list_geofences(
    auth: GeofenceRead, site_id: uuid.UUID | None = None, include_inactive: bool = False
) -> list[GeofenceOut]:
    if site_id is not None and not auth.scope.covers_site(site_id):
        raise AppError("NOT_FOUND")
    rows = auth.db.execute(
        text(
            _GEOFENCE_SELECT
            + " WHERE (CAST(:site AS uuid) IS NULL OR site_id = CAST(:site AS uuid))"
            + " AND (active OR :inactive) ORDER BY code"
        ),
        {"site": str(site_id) if site_id else None, "inactive": include_inactive},
    ).all()
    return [_geofence_out(r) for r in rows if auth.scope.covers_site(r.site_id)]


@router.post("/geofences", status_code=status.HTTP_201_CREATED, response_model=GeofenceOut)
def create_geofence(body: GeofenceCreate, auth: GeofenceManage) -> GeofenceOut:
    if active_site_in_scope(auth.db, auth.scope, body.site_id) is None:
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "site_id"}])
    ring = list(body.coordinates)
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    wkt = "POLYGON((" + ", ".join(f"{lon:.7f} {lat:.7f}" for lon, lat in ring) + "))"
    geofence_id = auth.db.execute(
        text(
            "INSERT INTO site_geofence (tenant_id, site_id, code, name, kind, area, created_by, updated_by) "
            "VALUES (CAST(:t AS uuid), CAST(:s AS uuid), :code, :name, :kind, ST_GeogFromText(:wkt), "
            "CAST(:u AS uuid), CAST(:u AS uuid)) RETURNING site_geofence_id"
        ),
        {
            "t": str(auth.tenant_id),
            "s": str(body.site_id),
            "code": body.code,
            "name": body.name,
            "kind": body.kind,
            "wkt": "SRID=4326;" + wkt,
            "u": str(auth.user_id),
        },
    ).scalar_one()
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        action="fleet.geofence.create",
        entity_type="site_geofence",
        entity_id=geofence_id,
        site_id=body.site_id,
        actor_user_id=auth.user_id,
        after={"code": body.code, "kind": body.kind, "vertices": len(ring) - 1},
    )
    out = _geofence_out(
        auth.db.execute(
            text(_GEOFENCE_SELECT + " WHERE site_geofence_id = CAST(:i AS uuid)"), {"i": str(geofence_id)}
        ).one()
    )
    auth.db.commit()
    return out


@router.post("/geofences/{site_geofence_id}/deactivate", response_model=GeofenceOut)
def deactivate_geofence(site_geofence_id: uuid.UUID, auth: GeofenceManage) -> GeofenceOut:
    row = auth.db.execute(
        text("SELECT site_id FROM site_geofence WHERE site_geofence_id = CAST(:i AS uuid) FOR UPDATE"),
        {"i": str(site_geofence_id)},
    ).one_or_none()
    if row is None or not auth.scope.covers_site(row.site_id):
        raise AppError("NOT_FOUND")
    auth.db.execute(
        text(
            "UPDATE site_geofence SET active = false, updated_by = CAST(:u AS uuid) "
            "WHERE site_geofence_id = CAST(:i AS uuid)"
        ),
        {"i": str(site_geofence_id), "u": str(auth.user_id)},
    )
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        action="fleet.geofence.deactivate",
        entity_type="site_geofence",
        entity_id=site_geofence_id,
        site_id=row.site_id,
        actor_user_id=auth.user_id,
    )
    out = _geofence_out(
        auth.db.execute(
            text(_GEOFENCE_SELECT + " WHERE site_geofence_id = CAST(:i AS uuid)"),
            {"i": str(site_geofence_id)},
        ).one()
    )
    auth.db.commit()
    return out


# --- Historique et événements de zone -------------------------------------------------------------------


def _window(
    auth: Authorized, period_start: datetime | None, period_end: datetime | None
) -> tuple[datetime, datetime]:
    now = auth.clock.now()
    end = min(period_end or now, now)
    start = period_start or end - timedelta(hours=6)
    if start >= end:
        raise AppError("END_BEFORE_START")
    if end - start > MAX_WINDOW:
        raise AppError("VALIDATION_ERROR", details=[{"field": "from", "type": "window_too_long"}])
    return start, end


def _geofences_of(auth: Authorized, site_ids: set[uuid.UUID]) -> dict[uuid.UUID, Any]:
    if not site_ids:
        return {}
    rows = auth.db.execute(
        text(
            "SELECT site_geofence_id, site_id, name, kind FROM site_geofence "
            "WHERE active AND site_id = ANY(CAST(:s AS uuid[]))"
        ),
        {"s": [str(s) for s in site_ids]},
    ).all()
    return {r.site_geofence_id: r for r in rows}


def _inside(
    auth: Authorized, position_ids: list[uuid.UUID], geofence_ids: set[uuid.UUID]
) -> dict[uuid.UUID, set[uuid.UUID]]:
    if not position_ids or not geofence_ids:
        return {}
    result: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for pid, gid in auth.db.execute(
        text(
            "SELECT p.gps_position_id, g.site_geofence_id FROM fleet_gps_position p "
            "JOIN site_geofence g ON g.site_geofence_id = ANY(CAST(:g AS uuid[])) "
            "AND ST_Covers(g.area, ST_SetSRID(ST_MakePoint(p.longitude, p.latitude), 4326)::geography) "
            "WHERE p.gps_position_id = ANY(CAST(:p AS uuid[]))"
        ),
        {"g": [str(g) for g in geofence_ids], "p": [str(p) for p in position_ids]},
    ).all():
        result[pid].add(gid)
    return result


def _audit_history(
    auth: Authorized,
    action: str,
    entity_id: uuid.UUID | None,
    site_id: uuid.UUID | None,
    purpose: str,
    start: datetime,
    end: datetime,
) -> None:
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        action=action,
        entity_type="vehicle" if entity_id else "site",
        entity_id=entity_id,
        site_id=site_id,
        actor_user_id=auth.user_id,
        reason=purpose,
        after={"from": start.isoformat(), "to": end.isoformat()},
    )


@router.get("/vehicles/{vehicle_id}/gps/track", response_model=TrackOut)
def vehicle_track(
    vehicle_id: uuid.UUID,
    auth: History,
    purpose: Purpose,
    period_start: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    period_end: Annotated[AwareDatetime | None, Query(alias="to")] = None,
) -> TrackOut:
    facts = vehicle_facts(auth.db, [vehicle_id]).get(vehicle_id)
    if facts is None or not auth.scope.covers_site(facts.site_id):
        raise AppError("NOT_FOUND")
    start, end = _window(auth, period_start, period_end)
    rows = list(
        auth.db.execute(
            select(FleetGpsPosition)
            .where(
                FleetGpsPosition.vehicle_id == vehicle_id,
                FleetGpsPosition.recorded_at >= start,
                FleetGpsPosition.recorded_at < end,
            )
            .order_by(FleetGpsPosition.recorded_at, FleetGpsPosition.gps_position_id)
            .limit(MAX_TRACK_POINTS + 1)
        ).scalars()
    )
    truncated = len(rows) > MAX_TRACK_POINTS
    rows = rows[:MAX_TRACK_POINTS]
    last = auth.db.execute(
        select(FleetGpsPosition.recorded_at)
        .where(FleetGpsPosition.vehicle_id == vehicle_id)
        .order_by(FleetGpsPosition.recorded_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    kept = usable(rows)
    fences = _geofences_of(auth, {facts.site_id})
    inside = _inside(auth, [p.gps_position_id for p in kept], set(fences))
    events = [
        GeofenceEvent(
            vehicle_id=vehicle_id,
            vehicle_fleet_number=facts.fleet_number,
            site_geofence_id=gid,
            geofence_name=fences[gid].name,
            geofence_kind=fences[gid].kind,
            event_type=kind,
            occurred_at=at,
        )
        for gid, kind, at in transitions(kept, inside, set(fences))
    ]
    _audit_history(auth, "fleet.gps.track.read", vehicle_id, facts.site_id, purpose, start, end)
    out = TrackOut(
        vehicle_id=vehicle_id,
        period_start=start,
        period_end=end,
        signal=signal(last, auth.clock.now()),
        last_recorded_at=last,
        points=[
            TrackPoint(
                latitude=p.latitude,
                longitude=p.longitude,
                speed_kmh=p.speed_kmh,
                accuracy_m=p.accuracy_m,
                recorded_at=p.recorded_at,
                received_at=p.received_at,
                late=p.received_at - p.recorded_at > LATE,
                source=p.source,
            )
            for p in rows
        ],
        truncated=truncated,
        distance_km=distance_km(kept),
        gaps=gaps(kept),
        stops=stops(kept),
        late_points=sum(1 for p in rows if p.received_at - p.recorded_at > LATE),
        ignored_points=len(rows) - len(kept),
        geofence_events=events,
    )
    auth.db.commit()
    return out


@router.get("/gps/geofence-events", response_model=list[GeofenceEvent])
def geofence_events(
    auth: History,
    site_id: uuid.UUID,
    purpose: Purpose,
    period_start: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    period_end: Annotated[AwareDatetime | None, Query(alias="to")] = None,
) -> list[GeofenceEvent]:
    """Entrées et sorties de zones de tous les engins d'un site sur la fenêtre (24 h max)."""
    if not auth.scope.covers_site(site_id):
        raise AppError("NOT_FOUND")
    start, end = _window(auth, period_start, period_end)
    rows = list(
        auth.db.execute(
            select(FleetGpsPosition)
            .where(
                FleetGpsPosition.site_id == site_id,
                FleetGpsPosition.recorded_at >= start,
                FleetGpsPosition.recorded_at < end,
            )
            .order_by(
                FleetGpsPosition.vehicle_id, FleetGpsPosition.recorded_at, FleetGpsPosition.gps_position_id
            )
            .limit(MAX_FEED_POSITIONS + 1)
        ).scalars()
    )
    if len(rows) > MAX_FEED_POSITIONS:
        raise AppError("VALIDATION_ERROR", details=[{"field": "from", "type": "too_many_positions"}])
    fences = _geofences_of(auth, {site_id})
    by_vehicle: dict[uuid.UUID, list[Any]] = defaultdict(list)
    for p in rows:
        by_vehicle[p.vehicle_id].append(p)
    kept_by_vehicle = {v: usable(points) for v, points in by_vehicle.items()}
    inside = _inside(
        auth, [p.gps_position_id for points in kept_by_vehicle.values() for p in points], set(fences)
    )
    fleet = vehicle_facts(auth.db, set(by_vehicle))
    events = [
        GeofenceEvent(
            vehicle_id=vid,
            vehicle_fleet_number=fleet[vid].fleet_number if vid in fleet else None,
            site_geofence_id=gid,
            geofence_name=fences[gid].name,
            geofence_kind=fences[gid].kind,
            event_type=kind,
            occurred_at=at,
        )
        for vid, points in kept_by_vehicle.items()
        for gid, kind, at in transitions(points, inside, set(fences))
    ]
    _audit_history(auth, "fleet.gps.geofence_events.read", None, site_id, purpose, start, end)
    auth.db.commit()
    return sorted(events, key=lambda e: (e.occurred_at, str(e.vehicle_id)))
