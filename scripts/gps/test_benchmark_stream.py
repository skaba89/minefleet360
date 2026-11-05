"""Tests du benchmark SSE avec données synthétiques sans réseau réel."""

import importlib.util
import io
import threading
import urllib.error
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

FILE = Path(__file__).with_name("benchmark_stream.py")
spec = importlib.util.spec_from_file_location("benchmark_stream", FILE)
assert spec and spec.loader
benchmark = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = benchmark
spec.loader.exec_module(benchmark)


class StubResponse:
    status = 200
    headers = {"Content-Type": "text/event-stream"}

    def __init__(self, body):
        self.lines = io.BytesIO(body)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def readline(self, size):
        return self.lines.readline(size)


class StreamBenchTests(TestCase):
    def test_requires_tls_outside_localhost(self):
        for url in ("http://example.com", "https://user:pass@example.com", "https://example.com?token=secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                benchmark.validate_base_url(url)
        self.assertEqual(benchmark.validate_base_url("http://127.0.0.1:8000/"), "http://127.0.0.1:8000")

    def test_never_returns_coordinates_or_token(self):
        response = StubResponse(
            b'event: snapshot\n'
            b'data: [{"latitude":9.4,"longitude":-13.5,"secret":"TOKEN"}]\n\n'
            b': heartbeat\n\n'
        )
        with patch.object(benchmark.urllib.request, "urlopen", return_value=response):
            result = benchmark.observe(
                "https://example.com", "TOKEN", None, threading.Barrier(1), 5, 1
            )
        self.assertEqual(result.status, 200)
        self.assertEqual(result.snapshots, 1)
        self.assertEqual(result.heartbeats, 1)
        report = str(benchmark.summarize([result]))
        for forbidden in ("latitude", "longitude", "TOKEN", "9.4", "-13.5"):
            self.assertNotIn(forbidden, report)

    def test_429_is_expected_saturation(self):
        with patch.object(
            benchmark.urllib.request,
            "urlopen",
            side_effect=urllib.error.HTTPError("https://example.com", 429, "limited", {}, None),
        ):
            result = benchmark.observe(
                "https://example.com", "dummy", None, threading.Barrier(1), 5, 1
            )
        self.assertEqual(result.failures, 0)
        self.assertEqual(benchmark.summarize([result])["http_429"], 1)

    def test_empty_and_percentiles(self):
        empty = benchmark.summarize([])
        self.assertIsNone(empty["first_frame_ms_p95"])
        self.assertIsNone(empty["first_frame_ms_p99"])
        self.assertEqual(empty["connection_failure_rate"], 0.0)
        results = [benchmark.Result(200, float(x), 1, 0, 0) for x in range(1, 21)]
        summary = benchmark.summarize(results)
        self.assertEqual(summary["first_frame_ms_p50"], 10.0)
        self.assertEqual(summary["first_frame_ms_p95"], 19.0)
        self.assertEqual(summary["first_frame_ms_p99"], 20.0)
        self.assertEqual(len(summary["samples"]), 20)
        self.assertEqual(summary["first_frame_missing"], 0)

    def test_invalid_content_type_is_failure(self):
        response = StubResponse(b'{"not":"stream"}')
        response.headers = {"Content-Type": "application/json"}
        with patch.object(benchmark.urllib.request, "urlopen", return_value=response):
            result = benchmark.observe(
                "https://example.com", "dummy", None, threading.Barrier(1), 5, 1
            )
        self.assertEqual(result.failures, 1)
