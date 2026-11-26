#!/usr/bin/env python3
"""Sonde de charge d'ingestion GPS (recette uniquement) : aucun secret, coordonnée ni IMEI en sortie.

Modes :
  - traceurs fournis par l'opérateur (recommandé staging) :
      MF_GPS_BENCH_TRACKERS='DEVICE_ID1=tok1 DEVICE_ID2=tok2'
  - provisioning local (base de démonstration uniquement) :
      MF_GPS_BENCH_TOKEN_ADMIN=<jeton fleet.gps.manage> --provision
Le provisioning n'associe que des véhicules SANS traceur actif ; il ne révoque
jamais une association existante sans --allow-revoke (manipulation destructrice).

Usage :
  MF_GPS_BENCH_URL=https://staging.example.org \
  MF_GPS_BENCH_TRACKERS='DEV1=tok1 DEV2=tok2' \
    python scripts/gps/benchmark_ingest.py --devices 2 --burst-points 10

Le rapport n'imprime que des compteurs, des percentiles et des codes d'erreur
stables. Un 409 (anti-rejeu, dédup ou anti-réaffectation : point antérieur à
l'association active) ou un 429 (limiteur) est compté séparément : ce sont des
comportements attendus sous rafale, pas des erreurs de protocole. Après un
provisioning, la sonde attend 3 s pour que chaque association soit active
depuis assez longtemps (sinon les premiers points sont refusés à juste titre).
"""

import argparse
import concurrent.futures
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

MAX_DEVICES = 8
MAX_BURST_POINTS = 100
MAX_SUSTAINED_SECONDS = 300
MIN_SPACING = 0.5

# Coordonnées synthétiques fixes (aucune donnée réelle) — jamais imprimées dans le rapport.
_SYNTH_BASE = (9.6410, -13.5780)


@dataclass
class IngestCounters:
    http_204: int = 0
    http_409: int = 0
    http_429: int = 0
    other: dict = field(default_factory=dict)
    latencies: list = field(default_factory=list)


def validate_base_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("URL must not contain credentials, query or fragment")
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1")
    ):
        raise ValueError("HTTPS required except localhost")
    if not parsed.hostname:
        raise ValueError("Host required")
    return url.rstrip("/")


def percentile(values: list[float], percent: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, (percent * len(ordered) + 99) // 100 - 1))
    return round(ordered[rank], 1)


def post_telemetry(
    base: str,
    token: str,
    device_id: str,
    sequence: int,
    recorded_at: datetime,
    timeout: float,
) -> tuple[int, str, float]:
    """Envoyer un point ; renvoyer (status, code d'erreur stable, latence client ms)."""
    lat_delta = (sequence % 17) * 0.0004
    body = {
        "device_id": device_id,
        "latitude": _SYNTH_BASE[0] + lat_delta,
        "longitude": _SYNTH_BASE[1] + (sequence % 23) * 0.0003,
        "recorded_at": recorded_at.isoformat(),
        "sequence": sequence,
        "speed_kmh": 30.0 + (sequence % 40),
        "accuracy_m": 8.0,
    }
    request = urllib.request.Request(
        base + "/api/v1/gps/telemetry",
        data=json.dumps(body).encode(),
        # Le jeton de provisioning est déjà préfixé « gps_ » ; la route dépouille
        # « Bearer gps_ » — ne jamais ajouter un second préfixe (sinon AUTH_REQUIRED).
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
            return response.status, "", (time.perf_counter() - started) * 1000
    except urllib.error.HTTPError as exc:
        # Ne jamais imprimer le corps : uniquement le code d'erreur stable.
        try:
            code = json.loads(exc.read() or b"{}").get("code", "")
        except ValueError:
            code = ""
        return exc.code, code, (time.perf_counter() - started) * 1000
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, "NETWORK", (time.perf_counter() - started) * 1000


def record(counters: IngestCounters, status: int, code: str, latency_ms: float) -> None:
    counters.latencies.append(latency_ms)
    if status == 204:
        counters.http_204 += 1
    elif status == 409:
        counters.http_409 += 1
    elif status == 429:
        counters.http_429 += 1
    else:
        key = f"{status}:{code}" if code else str(status)
        counters.other[key] = counters.other.get(key, 0) + 1


def device_loop(
    base: str,
    token: str,
    device_id: str,
    first_sequence: int,
    points: int,
    spacing: float,
    timeout: float,
    counters: IngestCounters,
) -> None:
    """Émettre `points` points avec recorded_at = maintenant − 1 s.

    L'appelant doit avoir attendu ≥ 3 s après un provisioning : la prévalidation
    refuse tout point antérieur à l'association active (anti-réaffectation,
    `position.recorded_at < binding.active_from` → 409 attendu et correct)."""
    for i in range(points):
        recorded_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        status, code, latency = post_telemetry(base, token, device_id, first_sequence + i, recorded_at, timeout)
        record(counters, status, code, latency)
        time.sleep(spacing)


def run_phase(base: str, trackers: dict[str, str], first_sequence: int, points: int, spacing: float,
              timeout: float) -> tuple[IngestCounters, float]:
    counters = IngestCounters()
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(len(trackers), 1)) as pool:
        futures = [
            pool.submit(device_loop, base, token, device_id, first_sequence, points, spacing,
                        timeout, counters)
            for device_id, token in trackers.items()
        ]
        for future in futures:
            future.result()
    return counters, time.perf_counter() - started


def counters_to_report(counters: IngestCounters, wall_seconds: float, points_sent: int) -> dict:
    lat = counters.latencies
    accepted_rate = counters.http_204 / wall_seconds if wall_seconds > 0 else 0.0
    return {
        "points_sent": points_sent,
        "http_204": counters.http_204,
        "http_409": counters.http_409,
        "http_429": counters.http_429,
        "other": dict(sorted(counters.other.items())),
        "wall_seconds": round(wall_seconds, 1),
        "accepted_per_second": round(accepted_rate, 2),
        "client_ms_p50": percentile(lat, 50),
        "client_ms_p95": percentile(lat, 95),
        "client_ms_p99": percentile(lat, 99),
    }


def fetch_gps_metrics(base: str, admin_token: str, timeout: float) -> dict | None:
    request = urllib.request.Request(
        base + "/api/v1/gps/metrics",
        headers={"Authorization": "Bearer " + admin_token, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read() or b"null")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


def provision_trackers(base: str, admin_token: str, count: int, allow_revoke: bool,
                       timeout: float) -> tuple[dict[str, str], list[str]]:
    """Associer `count` traceurs synthétiques à des véhicules sans traceur actif.

    Les jetons composites sont utilisés puis jamais imprimés. Aucune révocation
    d'association existante sans --allow-revoke (base de démonstration uniquement).
    """
    trackers: dict[str, str] = {}
    notes: list[str] = []
    request = urllib.request.Request(
        base + "/api/v1/vehicles?page=1&page_size=200",
        headers={"Authorization": "Bearer " + admin_token, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        vehicles = json.loads(response.read() or b"{}").get("items", [])
    for vehicle in vehicles:
        if len(trackers) >= count:
            break
        vehicle_id = vehicle["vehicle_id"]
        detail_req = urllib.request.Request(
            base + f"/api/v1/vehicles/{vehicle_id}/gps/tracker",
            headers={"Authorization": "Bearer " + admin_token, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(detail_req, timeout=timeout) as response:
                current = json.loads(response.read() or b"null")
            if current and current.get("revoked_at") is None:
                if not allow_revoke:
                    continue
                revoke_req = urllib.request.Request(
                    base + f"/api/v1/vehicles/{vehicle_id}/gps/tracker/revoke",
                    data=b"{}",
                    headers={"Authorization": "Bearer " + admin_token, "Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(revoke_req, timeout=timeout) as response:
                    response.read()
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                notes.append(f"vehicle_check:{exc.code}")
                continue
        except (urllib.error.URLError, TimeoutError, OSError):
            notes.append("vehicle_check:NETWORK")
            continue
        device_id = f"BENCH-{len(trackers) + 1:03d}"
        provision_req = urllib.request.Request(
            base + f"/api/v1/vehicles/{vehicle_id}/gps/tracker",
            data=json.dumps({"device_id": device_id}).encode(),
            headers={"Authorization": "Bearer " + admin_token, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(provision_req, timeout=timeout) as response:
                provisioned = json.loads(response.read() or b"{}")
            token = provisioned.get("token")
            if token:
                trackers[provisioned.get("device_id", device_id)] = token
            else:
                notes.append("provision:no_token")
        except urllib.error.HTTPError as exc:
            notes.append(f"provision:{exc.code}")
        except (urllib.error.URLError, TimeoutError, OSError):
            notes.append("provision:NETWORK")
    return trackers, notes


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled GPS ingestion load probe")
    parser.add_argument("--devices", type=int, default=3)
    parser.add_argument("--burst-points", type=int, default=10)
    parser.add_argument("--burst-spacing", type=float, default=0.6)
    parser.add_argument("--sustained-seconds", type=int, default=60)
    parser.add_argument("--sustained-spacing", type=float, default=2.5)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--skip-burst", action="store_true")
    parser.add_argument("--skip-sustained", action="store_true")
    parser.add_argument("--provision", action="store_true")
    parser.add_argument("--allow-revoke", action="store_true")
    args = parser.parse_args()

    if os.environ.get("MF_ENV") == "production":
        parser.error("This probe must not run in production")
    if not 1 <= args.devices <= MAX_DEVICES:
        parser.error(f"--devices must be between 1 and {MAX_DEVICES}")
    if not 1 <= args.burst_points <= MAX_BURST_POINTS:
        parser.error(f"--burst-points must be between 1 and {MAX_BURST_POINTS}")
    if not MIN_SPACING <= args.burst_spacing or not MIN_SPACING <= args.sustained_spacing:
        parser.error(f"spacings must be >= {MIN_SPACING} s")
    if not 1 <= args.sustained_seconds <= MAX_SUSTAINED_SECONDS:
        parser.error(f"--sustained-seconds must be between 1 and {MAX_SUSTAINED_SECONDS}")
    if not 1 <= args.timeout <= 60:
        parser.error("--timeout must be between 1 and 60")

    base_url = os.getenv("MF_GPS_BENCH_URL")
    admin_token = os.getenv("MF_GPS_BENCH_TOKEN_ADMIN")
    trackers_raw = os.getenv("MF_GPS_BENCH_TRACKERS", "")
    if not base_url:
        parser.error("MF_GPS_BENCH_URL is required")
    try:
        base = validate_base_url(base_url)
    except ValueError as exc:
        parser.error(str(exc))

    trackers: dict[str, str] = {}
    provisioning_notes: list[str] = []
    if trackers_raw.strip():
        for pair in trackers_raw.split():
            if "=" not in pair:
                parser.error("MF_GPS_BENCH_TRACKERS entries must be DEVICE_ID=token")
            device_id, token = pair.split("=", 1)
            trackers[device_id] = token
    elif args.provision:
        if not admin_token:
            parser.error("MF_GPS_BENCH_TOKEN_ADMIN is required with --provision")
        trackers, provisioning_notes = provision_trackers(
            base, admin_token, args.devices, args.allow_revoke, args.timeout
        )
    else:
        parser.error("provide MF_GPS_BENCH_TRACKERS or use --provision with MF_GPS_BENCH_TOKEN_ADMIN")
    trackers = dict(list(trackers.items())[: args.devices])
    if not trackers:
        parser.error("no tracker available for the probe")

    metrics_before = None
    # Jeton de lecture facultatif (fleet.gps.history — OPS_MANAGER/HSE/AUDITOR) :
    # /gps/metrics n'est pas porté par tous les jetons d'administration.
    read_token = os.getenv("MF_GPS_BENCH_TOKEN_READ") or admin_token
    if read_token:
        metrics_before = fetch_gps_metrics(base, read_token, args.timeout)
    report: dict = {
        "schema_version": "1.0",
        "benchmark_kind": "gps_ingest_load",
        "trackers_used": len(trackers),
        "provisioning_notes": provisioning_notes,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    if metrics_before is not None:
        report["metrics_before"] = metrics_before

    if not args.skip_burst:
        # Après un provisioning, attendre que chaque association soit active depuis
        # assez longtemps : la prévalidation refuse (409 correct) tout point dont
        # recorded_at précède active_from (protection anti-réaffectation).
        time.sleep(3)
        burst_counters, burst_wall = run_phase(
            base, trackers, 1, args.burst_points, args.burst_spacing, args.timeout
        )
        report["burst"] = counters_to_report(
            burst_counters, burst_wall, args.burst_points * len(trackers)
        )
    if not args.skip_sustained:
        seq_offset = (args.burst_points if not args.skip_burst else 0) + 100
        sustained_points = max(int(args.sustained_seconds / args.sustained_spacing), 1)
        sustained_counters, sustained_wall = run_phase(
            base, trackers, seq_offset, sustained_points, args.sustained_spacing, args.timeout
        )
        report["sustained"] = counters_to_report(
            sustained_counters, sustained_wall, sustained_points * len(trackers)
        )
    if read_token:
        metrics_after = fetch_gps_metrics(base, read_token, args.timeout)
        if metrics_after is not None:
            report["metrics_after"] = metrics_after

    print(json.dumps(report, indent=2))
    errors = sum(report["burst"]["other"].values()) if "burst" in report else 0
    errors += sum(report["sustained"]["other"].values()) if "sustained" in report else 0
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
