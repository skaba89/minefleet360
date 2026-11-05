"""Tests du harnais GPS sans réseau, ni identifiants réels."""
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

FILE = Path(__file__).with_name("benchmark_latest.py")
spec = importlib.util.spec_from_file_location("benchmark_latest", FILE)
assert spec and spec.loader
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class BenchmarkGpsTests(TestCase):
    def test_percentiles(self):
        self.assertEqual(benchmark.percentile([5, 1, 4, 3, 2], 50), 3)
        self.assertEqual(benchmark.percentile([5, 1, 4, 3, 2], 95), 5)
        with self.assertRaises(ValueError):
            benchmark.percentile([], 95)

    def test_age_must_be_timezone_aware(self):
        at = datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc)
        self.assertEqual(
            benchmark.position_age_seconds({"recorded_at": "2026-11-05T09:59:00Z"}, at),
            60,
        )
        self.assertIsNone(
            benchmark.position_age_seconds({"recorded_at": "2026-11-05T09:59:00"}, at)
        )
        self.assertIsNone(benchmark.position_age_seconds({}, at))

    def test_refuses_plaintext_remote_base(self):
        with self.assertRaises(ValueError):
            benchmark.collect("http://example.com", "fake", None, 1)

    def test_collect_never_returns_coordinates(self):
        from io import BytesIO

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, limit):
                return b'[{"recorded_at":"2026-11-05T09:59:00Z","latitude":9.3,"longitude":-13.4}]'

        with patch.object(benchmark.urllib.request, "urlopen", return_value=FakeResponse()):
            result = benchmark.collect("https://example.org", "dummy-token", None, 1)
        self.assertEqual(result["positions"], 1)
        self.assertNotIn("latitude", result)
        self.assertNotIn("longitude", result)
