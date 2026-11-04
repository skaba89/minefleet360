"""Lot 3 du générateur DEMO : GPS, zones et trajets.

- coordonnées de sites FICTIVES : placées dans la région annoncée mais décalées volontairement ; elles ne
  représentent aucune installation réelle (ni mine, ni port, ni atelier existant) ;
- zones par site (périmètre, chargement, déchargement, station carburant, atelier) créées par le service ;
- un traceur par engin de transport, provisionné par le service (jeton gardé en mémoire, jamais écrit) ;
- positions toutes les 2 minutes calées sur les événements réels de chaque rotation, envoyées par l'ingestion
  « passerelle authentifiée » (GPS-23, `accept_gps_telemetry_payload`) : JSON strict, secret du traceur,
  association, anti-rejeu par séquence, limites temporelles. Le limiteur anti-saturation de l'API traceur
  (60 points par minute RÉELLE) est propre aux appareils isolés et rendrait un rejeu d'historique
  impossible ; il n'est ni désactivé ni contourné en production. Les franchissements de zones sont calculés
  à la lecture par l'application ;
- le compteur kilométrique progresse de la distance réellement parcourue sur le tracé.

Données de suivi de véhicules FICTIFS uniquement : aucun suivi de personne réelle (CLAUDE.md).
"""

import itertools
import json
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from app.core.security import CompositeToken, parse_composite_token
from app.demo.runtime import as_actor, call, route
from app.fleet import gps_history, gps_live_service
from app.fleet.gps_gateway_ingestion import TrustedGatewayContext
from app.fleet.gps_live_schemas import TrackerCreateIn
from app.fleet.gps_payload_ingestion import accept_gps_telemetry_payload

if TYPE_CHECKING:
    import random

    from app.core.clock import FrozenClock
    from app.demo.catalog import Profile, TenantSpec
    from app.demo.generator import DemoReport
    from app.seed import _Actor

# Centres fictifs (lat, lon), décalés de plusieurs kilomètres des agglomérations et installations connues.
SITE_CENTERS: dict[str, tuple[float, float]] = {
    "BOKE-MINE": (11.0820, -13.8710),
    "BOFFA-PORT": (10.2510, -14.1120),
    "SIGUIRI-MINE": (11.5230, -9.0640),
    "KAMSAR-DEPOT": (10.7710, -14.4820),
    "CONAKRY-ATELIER": (9.7120, -13.4980),
}
# Décalages (m, est/nord) depuis le centre du site.
LOAD = (-3200.0, 900.0)
DUMP = (3600.0, -1500.0)
PARK = (0.0, 0.0)
FUEL = (180.0, 120.0)
WORKSHOP = (-220.0, -160.0)


def bearing_deg(previous: tuple[float, float] | None, lat: float, lon: float) -> float | None:
    """Cap du traceur simulé entre deux de ses points (0 = nord, sens horaire) ; None sans déplacement.

    Le traceur de démonstration joue le rôle de l'équipement : c'est lui qui « mesure » et transmet son cap,
    comme le ferait un boîtier réel. L'API ne calcule jamais de cap.
    """
    if previous is None or (previous[0] == lat and previous[1] == lon):
        return None
    phi1, phi2 = math.radians(previous[0]), math.radians(lat)
    dlon = math.radians(lon - previous[1])
    x = math.sin(dlon) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    return round(math.degrees(math.atan2(x, y)) % 360, 1) % 360


def offset(lat: float, lon: float, east_m: float, north_m: float) -> tuple[float, float]:
    return lat + north_m / 111_320.0, lon + east_m / (111_320.0 * math.cos(math.radians(lat)))


def path_km(points: list[tuple[datetime, float, float, float]]) -> float:
    return sum(gps_history.haversine_m(a[1], a[2], b[1], b[2]) for a, b in itertools.pairwise(points)) / 1000


def square(lat: float, lon: float, half_m: float) -> list[tuple[float, float]]:
    """Polygone carré en ordre GeoJSON [longitude, latitude]."""
    corners = [(-half_m, -half_m), (half_m, -half_m), (half_m, half_m), (-half_m, half_m)]
    return [(p[1], p[0]) for p in (offset(lat, lon, dx, dy) for dx, dy in corners)]


@dataclass
class Tracker:
    credential: CompositeToken
    device_id: str
    sequence: int = 0


class GpsMixin:
    if TYPE_CHECKING:
        spec: TenantSpec
        profile: Profile
        rng: random.Random
        clock: FrozenClock
        start: datetime
        report: DemoReport
        site_ids: dict[str, uuid.UUID]
        haulers: list[dict[str, Any]]

        def actor(self, role: str, site: str | None = None) -> _Actor: ...
        def at(self, moment: datetime) -> datetime: ...

    trackers: dict[uuid.UUID, Tracker]

    def point(self, site: str, where: tuple[float, float], jitter_m: float = 0.0) -> tuple[float, float]:
        lat, lon = SITE_CENTERS[site]
        dx = where[0] + (self.rng.uniform(-jitter_m, jitter_m) if jitter_m else 0.0)
        dy = where[1] + (self.rng.uniform(-jitter_m, jitter_m) if jitter_m else 0.0)
        return offset(lat, lon, dx, dy)

    # --- socle --------------------------------------------------------------------------------------
    def gps_setup(self) -> None:
        self.trackers = {}
        ops = self.actor("OPS_MANAGER")
        self.at(self.start + timedelta(hours=1, minutes=10))
        for site in self.spec.sites:
            lat, lon = SITE_CENTERS[site.code]
            zones = (
                ("PERIMETRE", "Périmètre du site", "SITE_BOUNDARY", PARK, 6000.0),
                ("CHARGEMENT", "Aire de chargement", "LOADING_AREA", LOAD, 250.0),
                ("DECHARGEMENT", "Aire de déchargement", "DUMP_AREA", DUMP, 300.0),
                ("CARBURANT", "Station carburant", "FUEL_STATION", FUEL, 60.0),
                ("ATELIER", "Atelier", "WORKSHOP", WORKSHOP, 80.0),
            )
            for code, name, kind, where, half in zones:
                clat, clon = offset(lat, lon, *where)
                route(
                    ops,
                    "fleet.geofence.manage",
                    gps_history.create_geofence,
                    gps_history.GeofenceCreate(
                        site_id=self.site_ids[site.code],
                        code=f"{code}-{site.code}"[:48],
                        name=f"{name} (DEMO)",
                        kind=kind,
                        coordinates=square(clat, clon, half),
                    ),
                )
                self.report.add("geofences")
        for hauler in self.haulers:
            device_id = f"DEMO-TRK-{hauler['fleet_number']}"
            out = call(
                ops,
                "fleet.gps.manage",
                gps_live_service.provision_tracker,
                hauler["vehicle_id"],
                TrackerCreateIn(device_id=device_id),
            )
            credential = parse_composite_token(out.token.removeprefix("gps_"))
            assert credential is not None
            self.trackers[hauler["vehicle_id"]] = Tracker(credential, device_id)
            self.report.add("gps_trackers")

    # --- trajets ---------------------------------------------------------------------------------------
    PHASES = {
        # événement de départ du tronçon → (origine, destination, à l'arrêt)
        "DEPARTED": (PARK, LOAD, False),
        "ARRIVED_LOADING": (LOAD, LOAD, True),
        "LOADED": (LOAD, DUMP, False),
        "ARRIVED_UNLOADING": (DUMP, DUMP, True),
        "UNLOADED": (DUMP, LOAD, False),
    }

    def gps_mission(
        self, hauler: dict[str, Any], timeline: list[tuple[str, datetime]], *, returns: bool
    ) -> None:
        """Positions le long de la mission ; retour au parc après la dernière rotation si `returns`."""
        site = hauler["site"]
        legs: list[tuple[datetime, datetime, tuple[float, float], tuple[float, float], bool]] = []
        for (kind, t0), (next_kind, t1) in itertools.pairwise(timeline):
            if kind == "UNLOADED" and next_kind in ("COMPLETED", "SUSPENDED"):
                legs.append((t0, t1, DUMP, PARK if returns else DUMP, not returns))
            elif kind in self.PHASES:
                origin, dest, still = self.PHASES[kind]
                legs.append((t0, t1, origin, dest, still))
        points: list[tuple[datetime, float, float, float]] = []
        for t0, t1, origin, dest, still in legs:
            duration = (t1 - t0).total_seconds()
            if duration <= 0:
                continue
            t = t0
            while t < t1:
                f = (t - t0).total_seconds() / duration
                where = (origin[0] + (dest[0] - origin[0]) * f, origin[1] + (dest[1] - origin[1]) * f)
                lat, lon = self.point(site, where, jitter_m=12.0 if still else 25.0)
                speed = 0.0 if still else math.dist(origin, dest) / duration * 3.6
                points.append((t, lat, lon, round(speed * self.rng.uniform(0.85, 1.1), 1)))
                t += timedelta(minutes=self.profile.gps_step_minutes)
        gps_days = self.profile.gps_days
        if (
            gps_days is not None
            and points
            and points[0][0] < self.start + timedelta(days=self.profile.days - gps_days)
        ):
            # Hors fenêtre d'historique GPS : aucune position envoyée ; le compteur km suit le tracé.
            hauler["km"] += Decimal(str(round(path_km(points), 1)))
            return
        self._send(hauler, points)

    def _send(self, hauler: dict[str, Any], points: list[tuple[datetime, float, float, float]]) -> None:
        if not points:
            return
        tracker = self.trackers[hauler["vehicle_id"]]
        # Session sous contexte RLS de la société (posé par la tenancy) ; une transaction par mission.
        with as_actor(self.actor("OPS_MANAGER"), "fleet.gps.manage") as auth:
            db = auth.db
            km = 0.0
            previous: tuple[float, float] | None = None
            for recorded, lat, lon, speed in points:
                tracker.sequence += 1
                payload = json.dumps(
                    {
                        "device_id": tracker.device_id,
                        "latitude": round(lat, 6),
                        "longitude": round(lon, 6),
                        "recorded_at": recorded.isoformat(),
                        "sequence": tracker.sequence,
                        "speed_kmh": speed,
                        "heading_deg": bearing_deg(previous, round(lat, 6), round(lon, 6)),
                        "accuracy_m": round(self.rng.uniform(4.0, 12.0), 1),
                    }
                ).encode()
                received = recorded + timedelta(seconds=self.rng.randint(2, 20))
                self.clock.set(received)
                accepted = accept_gps_telemetry_payload(
                    db,
                    context=TrustedGatewayContext(tracker.credential.tenant_id),
                    payload=payload,
                    supplied_secret=tracker.credential.secret,
                    received_at=received,
                )
                if not accepted:
                    raise RuntimeError(f"position refusée par l'ingestion GPS ({tracker.device_id})")
                if previous is not None:
                    km += gps_history.haversine_m(previous[0], previous[1], lat, lon) / 1000
                previous = (lat, lon)
                self.report.add("gps_positions")
            db.commit()
        hauler["km"] += Decimal(str(round(km, 1)))
