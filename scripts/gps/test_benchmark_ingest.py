"""Tests de la sonde d'ingestion GPS avec données synthétiques sans réseau réel."""

import importlib.util
import io
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

FILE = Path(__file__).with_name("benchmark_ingest.py")
spec = importlib.util.spec_from_file_location("benchmark_ingest", FILE)
assert spec and spec.loader
benchmark = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = benchmark
spec.loader.exec_module(benchmark)


class StubResponse:
    status = 204

    def __init__(self, body=b""):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return self._body


class IngestProbeTests(TestCase):
    def test_requires_tls_outside_localhost(self):
        for url in ("http://example.com", "https://user:pass@example.com", "https://example.com?token=secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                benchmark.validate_base_url(url)
        self.assertEqual(benchmark.validate_base_url("http://127.0.0.1:8000/"), "http://127.0.0.1:8000")

    def test_record_classifies_statuses(self):
        counters = benchmark.IngestCounters()
        benchmark.record(counters, 204, "", 12.0)
        benchmark.record(counters, 409, "", 15.0)
        benchmark.record(counters, 409, "", 14.0)
        benchmark.record(counters, 429, "", 9.0)
        benchmark.record(counters, 400, "VALIDATION_ERROR", 8.0)
        self.assertEqual(counters.http_204, 1)
        self.assertEqual(counters.http_409, 2)
        self.assertEqual(counters.http_429, 1)
        self.assertEqual(counters.other, {"400:VALIDATION_ERROR": 1})

    def test_report_never_contains_token_device_or_coordinates(self):
        counters = benchmark.IngestCounters()
        for latency in (10.0, 20.0, 30.0):
            benchmark.record(counters, 204, "", latency)
        report = str(benchmark.counters_to_report(counters, 3.0, 3))
        for forbidden in ("TOKEN", "gps_", "BENCH-", "9.6410", "-13.5780", "latitude", "longitude"):
            self.assertNotIn(forbidden, report)
        self.assertIn("client_ms_p50", report)

    def test_percentiles_and_empty(self):
        self.assertIsNone(benchmark.percentile([], 95))
        values = [float(x) for x in range(1, 21)]
        self.assertEqual(benchmark.percentile(values, 50), 10.0)
        self.assertEqual(benchmark.percentile(values, 95), 19.0)
        self.assertEqual(benchmark.percentile(values, 99), 20.0)

    def test_204_with_body_and_error_code_extraction(self):
        with patch.object(benchmark.urllib.request, "urlopen", return_value=StubResponse(b"")):
            status, code, latency = benchmark.post_telemetry(
                "http://127.0.0.1:8000", "TOKEN", "DEV-1", 1, datetime.now(timezone.utc), 5
            )
        self.assertEqual((status, code), (204, ""))
        self.assertGreaterEqual(latency, 0.0)

    def test_http_error_keeps_only_stable_code(self):
        error = urllib.error.HTTPError(
            "https://example.com", 409, "conflict", {},
            io.BytesIO(json.dumps({"code": "CONFLICT", "message_fr": "Message GPS refusé, ancien ou déjà reçu."}).encode()),
        )
        with patch.object(benchmark.urllib.request, "urlopen", side_effect=error):
            status, code, _ = benchmark.post_telemetry(
                "https://example.com", "TOKEN", "DEV-1", 1, datetime.now(timezone.utc), 5
            )
        self.assertEqual((status, code), (409, "CONFLICT"))

    def test_network_failure_is_tagged(self):
        with patch.object(benchmark.urllib.request, "urlopen", side_effect=TimeoutError("timed out")):
            status, code, _ = benchmark.post_telemetry(
                "http://127.0.0.1:8000", "TOKEN", "DEV-1", 1, datetime.now(timezone.utc), 5
            )
        self.assertEqual((status, code), (0, "NETWORK"))

    def test_authorization_uses_provisioning_token_without_second_prefix(self):
        """Le jeton de provisioning est déjà préfixé gps_ : l'en-tête ne doit pas doubler le préfixe."""
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["authorization"] = request.headers.get("Authorization")
            return StubResponse(b"")

        with patch.object(benchmark.urllib.request, "urlopen", side_effect=fake_urlopen):
            benchmark.post_telemetry(
                "http://127.0.0.1:8000", "gps_ABC.DEF.GHI", "DEV-1", 1, datetime.now(timezone.utc), 5
            )
        self.assertEqual(captured["authorization"], "Bearer gps_ABC.DEF.GHI")
        self.assertNotIn("Bearer gps_gps_", captured["authorization"])

    def test_device_loop_records_synthetic_sequence(self):
        counters = benchmark.IngestCounters()
        with patch.object(benchmark, "post_telemetry", return_value=(204, "", 5.0)) as probe:
            benchmark.device_loop("http://127.0.0.1:8000", "TOKEN", "DEV-1", 1, 3, 0.0, 5, counters)
        self.assertEqual(counters.http_204, 3)
        sequences = [call_args.args[3] for call_args in probe.call_args_list]
        self.assertEqual(sequences, [1, 2, 3])
