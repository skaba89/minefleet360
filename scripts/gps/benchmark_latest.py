#!/usr/bin/env python3
"""Benchmark lecture GPS existante, sans journaliser jetons ni coordonnées.

Exemple (recette seulement):
  MF_GPS_BENCH_URL=https://recette.example.org MF_GPS_BENCH_TOKEN=... \
      python scripts/gps/benchmark_latest.py --samples 20 --interval 1
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def percentile(values: list[float], percent: float) -> float:
    """Nearest-rank percentile; suitable for a small sample, not an SLO proof."""
    if not values:
        raise ValueError("échantillon vide")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, (int((percent / 100 * len(ordered) + 0.999999)) - 1)))
    return ordered[index]


def validate_base_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("URL sans identifiants, query ni fragment requise")
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1")
    ):
        raise ValueError("HTTPS obligatoire hors localhost")
    if not parsed.hostname:
        raise ValueError("hôte requis")
    return url.rstrip("/")


def position_age_seconds(position: dict, observed_at: datetime) -> float | None:
    """Heuristic device-to-observer age. Clock offsets can bias this metric."""
    try:
        timestamp = datetime.fromisoformat(position["recorded_at"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            return None
        return (observed_at - timestamp).total_seconds()
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def collect(url: str, token: str, site_id: str | None, timeout: float) -> dict:
    base = validate_base_url(url)
    endpoint = base + "/api/v1/vehicles/gps/latest"
    if site_id:
        endpoint += "?" + urllib.parse.urlencode({"site_id": site_id})
    request = urllib.request.Request(
        endpoint,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(5_000_001)
        if len(raw) > 5_000_000:
            raise ValueError("réponse GPS > 5 Mo")
        positions = json.loads(raw)
    elapsed_ms = (time.perf_counter() - start) * 1000
    if not isinstance(positions, list):
        raise ValueError("la réponse GPS n'est pas une liste")
    observed_at = datetime.now(timezone.utc)
    ages = [position_age_seconds(p, observed_at) for p in positions if isinstance(p, dict)]
    valid_ages = [a for a in ages if a is not None]
    return {
        "http_ms": round(elapsed_ms, 2),
        "positions": len(positions),
        "oldest_recorded_age_s": round(max(valid_ages), 2) if valid_ages else None,
    }


def summarize(samples: list[dict], total_requests: int, failures: int) -> dict:
    latencies = [sample["http_ms"] for sample in samples]
    successes = len(samples)
    return {
        "schema_version": "1.0",
        "benchmark_kind": "gps_latest_rest",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "total_requests": total_requests,
        "successes": successes,
        "failures": failures,
        "success_rate": round(successes / total_requests, 4),
        "failure_rate": round(failures / total_requests, 4),
        "http_latency_ms": {
            "p50": percentile(latencies, 50) if latencies else None,
            "p95": percentile(latencies, 95) if latencies else None,
            "p99": percentile(latencies, 99) if latencies else None,
            "max": max(latencies) if latencies else None,
        },
        "max_observed_positions": max((sample["positions"] for sample in samples), default=0),
        # Sanitized individual measurements: no coordinates, vehicle IDs or tokens.
        "samples": samples,
        "note": "REST polling baseline only; not ingestion-to-screen latency or SSE throughput",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Mesure de référence de la lecture GPS")
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--site-id", default=None)
    args = parser.parse_args()
    if os.environ.get("MF_ENV") == "production":
        parser.error("ce benchmark ne doit pas être exécuté en production")
    if not 1 <= args.samples <= 200 or not 0 <= args.interval <= 60 or not 0 < args.timeout <= 60:
        parser.error("samples 1..200, interval 0..60, timeout (0, 60]")
    url, token = os.getenv("MF_GPS_BENCH_URL"), os.getenv("MF_GPS_BENCH_TOKEN")
    if not url or not token:
        parser.error("MF_GPS_BENCH_URL et MF_GPS_BENCH_TOKEN requis")
    samples: list[dict] = []
    failures = 0
    for i in range(args.samples):
        try:
            samples.append(collect(url, token, args.site_id, args.timeout))
        except urllib.error.HTTPError as exc:
            failures += 1
            if exc.code in (401, 403):
                print("Authentification ou autorisation refusée; arrêt.", file=sys.stderr)
                return 2
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
            failures += 1
        if i < args.samples - 1:
            time.sleep(args.interval)
    report = summarize(samples, args.samples, failures)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
