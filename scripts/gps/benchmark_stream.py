#!/usr/bin/env python3
"""SSE GPS load probe (staging only): no coordinates, tokens, or raw payloads in output.

Usage:
  MF_GPS_BENCH_URL=https://staging.example.org MF_GPS_BENCH_TOKEN=... \
    python scripts/gps/benchmark_stream.py --concurrency 10 --hold-seconds 5
"""

import argparse
import concurrent.futures
import json
import os
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Result:
    status: int
    first_event_ms: float | None
    snapshots: int
    heartbeats: int
    failures: int


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


def observe(
    base: str,
    token: str,
    site_id: str | None,
    barrier: threading.Barrier,
    hold_seconds: float,
    timeout: float,
) -> Result:
    path = base + "/api/v1/vehicles/gps/stream"
    if site_id:
        path += "?" + urllib.parse.urlencode({"site_id": site_id})
    request = urllib.request.Request(
        path,
        headers={"Authorization": "Bearer " + token, "Accept": "text/event-stream"},
    )
    try:
        barrier.wait(timeout=timeout)
    except threading.BrokenBarrierError:
        return Result(0, None, 0, 0, 1)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if "text/event-stream" not in response.headers.get("Content-Type", ""):
                return Result(response.status, None, 0, 0, 1)
            deadline = started + hold_seconds
            first_ms: float | None = None
            snapshots = heartbeats = 0
            consumed = 0
            while time.perf_counter() < deadline:
                line = response.readline(8193)
                consumed += len(line)
                if len(line) > 8192 or consumed > 3_000_000:
                    return Result(response.status, first_ms, snapshots, heartbeats, 1)
                if not line:
                    break
                if first_ms is None:
                    first_ms = (time.perf_counter() - started) * 1000
                # Never parse or retain "data:" (GPS/PII); inspect only SSE metadata.
                if line.startswith(b"event: snapshot"):
                    snapshots += 1
                elif line.startswith(b": heartbeat"):
                    heartbeats += 1
            return Result(response.status, first_ms, snapshots, heartbeats, 0)
    except urllib.error.HTTPError as exc:
        # Do not print response body, which could contain tenant information.
        return Result(exc.code, None, 0, 0, 0 if exc.code == 429 else 1)
    except (urllib.error.URLError, TimeoutError, OSError):
        return Result(0, None, 0, 0, 1)


def summarize(results: list[Result]) -> dict:
    times = sorted(r.first_event_ms for r in results if r.first_event_ms is not None)

    def percentile(p: int) -> float | None:
        if not times:
            return None
        rank = max(0, min(len(times) - 1, (p * len(times) + 99) // 100 - 1))
        return round(times[rank], 1)

    return {
        "connections": len(results),
        "http_200": sum(r.status == 200 for r in results),
        "http_429": sum(r.status == 429 for r in results),
        "http_401_403": sum(r.status in (401, 403) for r in results),
        "errors": sum(r.failures for r in results),
        "first_frame_ms_p50": percentile(50),
        "first_frame_ms_p95": percentile(95),
        "snapshots_seen": sum(r.snapshots for r in results),
        "heartbeats_seen": sum(r.heartbeats for r in results),
        "note": "Measurement at HTTP client, not ingestion-to-screen latency or device validation",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled GPS SSE staging concurrency probe")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--hold-seconds", type=float, default=5)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--site-id")
    args = parser.parse_args()
    if not 1 <= args.concurrency <= 64:
        parser.error("--concurrency must be between 1 and 64")
    if not 1 <= args.hold_seconds <= 15 or not 1 <= args.timeout <= 30:
        parser.error("--hold-seconds 1..15, --timeout 1..30")
    if os.environ.get("MF_ENV") == "production":
        parser.error("This probe must not run in production")
    url, token = os.getenv("MF_GPS_BENCH_URL"), os.getenv("MF_GPS_BENCH_TOKEN")
    if not url or not token:
        parser.error("MF_GPS_BENCH_URL and MF_GPS_BENCH_TOKEN are required")
    try:
        base = validate_base_url(url)
    except ValueError as exc:
        parser.error(str(exc))
    barrier = threading.Barrier(args.concurrency)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [
            pool.submit(observe, base, token, args.site_id, barrier, args.hold_seconds, args.timeout)
            for _ in range(args.concurrency)
        ]
        results = [f.result() for f in futures]
    report = summarize(results)
    report["observed_at"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(report, indent=2))
    # 429 is expected when probing capacity, but unauthorized and failures are errors.
    return 0 if report["errors"] == 0 and report["http_401_403"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
