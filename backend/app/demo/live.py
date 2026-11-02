"""`minefleet demo live-feed` : émetteur GPS de démonstration pendant une présentation.

- refusé hors base DEMO (mêmes garde-fous que `demo seed`) ;
- renouvelle le traceur de chaque engin de transport DEMO disponible (révocation + provisionnement par les
  services, audités) : les secrets ne sont jamais stockés, il faut donc en émettre de nouveaux ; ils restent
  en mémoire le temps de l'émission ;
- envoie une position par engin et par intervalle par la VRAIE API traceur (`POST /api/v1/gps/telemetry`,
  `Authorization: Bearer gps_…`), comme un boîtier : authentification, limites et anti-rejeu s'appliquent ;
- ne produit QUE des positions (aller-retour aire de chargement ↔ aire de déchargement) : aucune mission,
  aucun événement, aucune pesée n'est inventé ;
- API locale uniquement (le jeton circule en clair sur la boucle locale, jamais sur le réseau).
"""

import json
import math
import re
import time as systime
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.clock import SystemClock
from app.core.config import Settings, get_settings
from app.demo.catalog import TENANTS
from app.demo.gps import DUMP, LOAD, PARK, SITE_CENTERS, offset
from app.demo.guards import DemoRefused, ensure_demo_database
from app.demo.runtime import as_actor, call
from app.demo.verify import _tenant
from app.fleet import gps_live_service
from app.fleet.gps_binding_models import FleetGpsDeviceBinding
from app.fleet.gps_live_schemas import TrackerCreateIn
from app.fleet.models import Vehicle
from app.organization.models import Site
from app.seed import _Actor, _user_id

LOCAL_API = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d+)?$")
# Cycle d'un aller-retour (minutes) : route vers le chargement, chargement, route chargée, déchargement.
LEGS: tuple[tuple[float, tuple[float, float], tuple[float, float]], ...] = (
    (14.0, LOAD, LOAD),
    (22.0, LOAD, DUMP),
    (6.0, DUMP, DUMP),
    (20.0, DUMP, LOAD),
)
CYCLE = sum(minutes for minutes, _, _ in LEGS)

Sender = Callable[[str, bytes], int]


@dataclass
class Emitter:
    vehicle_id: uuid.UUID
    fleet_number: str
    site_code: str
    token: str
    device_id: str
    phase_min: float
    active_from: datetime
    sequence: int = 0


@dataclass
class FeedReport:
    trackers: int = 0
    sent: int = 0
    accepted: int = 0
    refused: dict[int, int] = field(default_factory=dict)


def position(e: Emitter, now: datetime, start: datetime) -> tuple[float, float, float]:
    """Position sur le cycle chargement ↔ déchargement à l'instant `now` (lat, lon, vitesse km/h)."""
    t = ((now - start).total_seconds() / 60 + e.phase_min) % CYCLE
    for minutes, origin, dest in LEGS:
        if t <= minutes:
            f = t / minutes
            east = origin[0] + (dest[0] - origin[0]) * f
            north = origin[1] + (dest[1] - origin[1]) * f
            lat, lon = offset(*SITE_CENTERS[e.site_code], east, north)
            speed = math.dist(origin, dest) / (minutes * 60) * 3.6
            return lat, lon, round(speed, 1)
        t -= minutes
    lat, lon = offset(*SITE_CENTERS[e.site_code], *PARK)  # inatteignable : t < CYCLE
    return lat, lon, 0.0


def http_sender(api_url: str) -> Sender:
    if not LOCAL_API.match(api_url):
        raise DemoRefused(f"API locale exigée pour l'émetteur DEMO (reçu {api_url})")

    def send(token: str, payload: bytes) -> int:
        request = urllib.request.Request(  # noqa: S310 (URL locale contrôlée ci-dessus)
            f"{api_url}/api/v1/gps/telemetry",
            data=payload,
            method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
                return int(response.status)
        except urllib.error.HTTPError as exc:
            return int(exc.code)

    return send


def prepare(settings: Settings | None = None) -> list[Emitter]:
    """Renouvelle les traceurs des engins DEMO disponibles et retourne les émetteurs (jetons en mémoire)."""
    ensure_demo_database(settings or get_settings())
    clock = SystemClock()
    emitters: list[Emitter] = []
    for spec in TENANTS:
        tenant = _tenant(spec.code)
        if tenant is None or not tenant.is_demo:
            continue
        tenant_id = tenant.tenant_id
        ops = _Actor(
            tenant_id, _user_id(tenant_id, f"ops-manager@{spec.code}.example.com"), "CUSTOMER", clock
        )
        with as_actor(ops, "fleet.gps.manage") as auth:
            rows = auth.db.execute(
                select(Vehicle.vehicle_id, Vehicle.fleet_number, Site.code, FleetGpsDeviceBinding.device_id)
                .join(Site, Site.site_id == Vehicle.site_id)
                .join(FleetGpsDeviceBinding, FleetGpsDeviceBinding.vehicle_id == Vehicle.vehicle_id)
                .where(
                    Vehicle.status == "AVAILABLE",
                    FleetGpsDeviceBinding.revoked_at.is_(None),
                    FleetGpsDeviceBinding.device_id.like("DEMO-TRK-%"),
                )
                .order_by(Vehicle.fleet_number)
            ).all()
        for index, (vehicle_id, fleet_number, site_code, device_id) in enumerate(rows):
            if site_code not in SITE_CENTERS:
                continue
            call(ops, "fleet.gps.manage", gps_live_service.revoke_tracker, vehicle_id)
            out = call(
                ops,
                "fleet.gps.manage",
                gps_live_service.provision_tracker,
                vehicle_id,
                TrackerCreateIn(device_id=device_id),
            )
            emitters.append(
                Emitter(
                    vehicle_id,
                    fleet_number,
                    site_code,
                    out.token,
                    device_id,
                    phase_min=(index * 11.0) % CYCLE,
                    active_from=out.active_from,
                )
            )
    return emitters


def tick(emitters: list[Emitter], send: Sender, now: datetime, start: datetime, report: FeedReport) -> None:
    for e in emitters:
        lat, lon, speed = position(e, now, start)
        e.sequence += 1
        payload = json.dumps(
            {
                "device_id": e.device_id,
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                # Jamais avant l'activation du traceur renouvelé (refus anti-attribution, GPS-23).
                "recorded_at": max(now - timedelta(seconds=2), e.active_from).isoformat(),
                "sequence": e.sequence,
                "speed_kmh": speed,
                "accuracy_m": 6.0,
            }
        ).encode()
        status = send(e.token, payload)
        report.sent += 1
        if status == 204:
            report.accepted += 1
        else:
            report.refused[status] = report.refused.get(status, 0) + 1


def live_feed(
    *,
    send: Sender,
    interval_s: float,
    duration_min: float,
    settings: Settings | None = None,
    sleep: Callable[[float], None] = systime.sleep,
) -> FeedReport:
    emitters = prepare(settings)
    report = FeedReport(trackers=len(emitters))
    if not emitters:
        return report
    clock = SystemClock()
    start = clock.now()
    end = start + timedelta(minutes=duration_min)
    while True:
        now = clock.now()
        tick(emitters, send, now, start, report)
        if now + timedelta(seconds=interval_s) >= end:
            return report
        sleep(interval_s)
