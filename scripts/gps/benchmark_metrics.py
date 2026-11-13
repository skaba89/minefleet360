#!/usr/bin/env python3
"""Relève des agrégats SLO GPS (`/gps/metrics`, #438) — prérequis n°6 du GO/NO-GO.

Lecture seule : la réponse est un objet d'agrégats (aucune position, aucun
identifiant de véhicule, aucun jeton) ; le rapport horodaté sert de preuve pour
la signature des seuils. La signature des seuils elle-même reste une étape
humaine, séparée de cette relève.

Exemple (recette seulement):
  MF_GPS_BENCH_URL=https://staging.example.org MF_GPS_BENCH_TOKEN=... \
      python scripts/gps/benchmark_metrics.py --minutes 60 --minutes 1440 --samples 20
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime


def percentile(values: list[float], percent: float) -> float:
    """Nearest-rank percentile; suitable for a small sample, not an SLO proof."""
    if not values:
        raise ValueError("échantillon vide")
    ordered = sorted(values)
    index = max(
        0, min(len(ordered) - 1, int(percent / 100 * len(ordered) + 0.999999) - 1)
    )
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


def collect(url: str, token: str, minutes: int, timeout: float) -> dict:
    base = validate_base_url(url)
    endpoint = (
        base + "/api/v1/gps/metrics?" + urllib.parse.urlencode({"minutes": minutes})
    )
    request = urllib.request.Request(
        endpoint,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    start = time.perf_counter()
    # Schéma validé par validate_base_url (HTTPS hors localhost, sans identifiants) : noqa S310.
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError("réponse métriques > 1 Mo")
        metrics = json.loads(raw)
    elapsed_ms = (time.perf_counter() - start) * 1000
    if not isinstance(metrics, dict):
        raise ValueError("la réponse métriques n'est pas un objet d'agrégats")
    if metrics.get("window_minutes") != minutes:
        raise ValueError("fenêtre renvoyée différente de la fenêtre demandée")
    return {"http_ms": round(elapsed_ms, 2), "metrics": metrics}


def summarize(windows: dict[int, dict], total_requests: int, failures: int) -> dict:
    per_window: dict[str, dict] = {}
    for minutes, data in sorted(windows.items()):
        samples = data["samples"]
        latencies = [sample["http_ms"] for sample in samples]
        successes = len(samples)
        per_window[str(minutes)] = {
            "requests": data["requests"],
            "successes": successes,
            "failures": data["failures"],
            "http_latency_ms": {
                "p50": percentile(latencies, 50) if latencies else None,
                "p95": percentile(latencies, 95) if latencies else None,
                "p99": percentile(latencies, 99) if latencies else None,
                "max": max(latencies) if latencies else None,
            },
            # Dernière réponse réussie : agrégats SLO bruts, sans position ni identifiant.
            "aggregates_observed": samples[-1]["metrics"] if samples else None,
        }
    return {
        "schema_version": "1.0",
        "benchmark_kind": "gps_metrics_slo",
        "observed_at": datetime.now(UTC).isoformat(),
        "total_requests": total_requests,
        "successes": total_requests - failures,
        "failures": failures,
        "success_rate": round((total_requests - failures) / total_requests, 4)
        if total_requests
        else 0,
        "windows": per_window,
        "note": (
            "Agrégats SLO relevés à l'instant de la session ; la signature des seuils "
            "cibles reste une décision humaine séparée (prérequis n°6)."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Relève des agrégats SLO GPS de recette"
    )
    parser.add_argument(
        "--minutes",
        action="append",
        type=int,
        default=None,
        help="fenêtre en minutes (1..1440) ; répétable, défaut : 60 et 1440",
    )
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    if os.environ.get("MF_ENV") == "production":
        parser.error("cette relève ne doit pas être exécutée en production")
    minutes_list = args.minutes if args.minutes else [60, 1440]
    if not all(1 <= minutes <= 1440 for minutes in minutes_list):
        parser.error("chaque fenêtre minutes doit être dans 1..1440")
    if (
        not 1 <= args.samples <= 200
        or not 0 <= args.interval <= 60
        or not 0 < args.timeout <= 60
    ):
        parser.error("samples 1..200, interval 0..60, timeout (0, 60]")
    url, token = os.getenv("MF_GPS_BENCH_URL"), os.getenv("MF_GPS_BENCH_TOKEN")
    if not url or not token:
        parser.error("MF_GPS_BENCH_URL et MF_GPS_BENCH_TOKEN requis")
    windows: dict[int, dict] = {}
    failures = 0
    total_requests = 0
    for minutes in minutes_list:
        samples: list[dict] = []
        window_failures = 0
        for i in range(args.samples):
            total_requests += 1
            try:
                samples.append(collect(url, token, minutes, args.timeout))
            except urllib.error.HTTPError as exc:
                window_failures += 1
                if exc.code in (401, 403):
                    print(
                        "Authentification ou autorisation refusée; arrêt.",
                        file=sys.stderr,
                    )
                    return 2
            except (
                urllib.error.URLError,
                TimeoutError,
                ValueError,
                json.JSONDecodeError,
            ):
                window_failures += 1
            if i < args.samples - 1:
                time.sleep(args.interval)
        failures += window_failures
        windows[minutes] = {
            "requests": args.samples,
            "failures": window_failures,
            "samples": samples,
        }
    report = summarize(windows, total_requests, failures)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
