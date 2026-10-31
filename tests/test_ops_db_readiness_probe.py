"""Tests for unprivileged database readiness probe without live network."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "infra/deploy/probe-database.sh"


class ReadinessProbeTests(unittest.TestCase):
    def _run(self, result: str, exit_code: int = 0):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "curl"
            fake.write_text(f"#!/bin/sh\nprintf '%s' '{result}'\nexit {exit_code}\n")
            fake.chmod(0o700)
            env = {**os.environ, "PATH": directory + ":" + os.environ["PATH"],
                   "MINEFLEET_BASE_URL": "https://staging.example.invalid"}
            return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)

    def test_healthy_readiness(self):
        self.assertEqual(self._run("200").returncode, 0)

    def test_failing_database_readiness(self):
        self.assertEqual(self._run("503").returncode, 2)

    def test_transport_failure(self):
        self.assertEqual(self._run("000", 7).returncode, 2)

    def test_http_origin_required(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, "MINEFLEET_BASE_URL": "http://localhost"}
            check = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True)
            self.assertEqual(check.returncode, 3)


if __name__ == "__main__":
    unittest.main()
