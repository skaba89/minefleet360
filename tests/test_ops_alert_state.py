"""Unit tests for the operational alert transition logic (no Docker/network required)."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "infra" / "deploy" / "alert-state.py"
spec = importlib.util.spec_from_file_location("alert_state", path)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class AlertStateTests(unittest.TestCase):
    def test_alert_only_after_threshold_and_single_recovery(self):
        state = {}
        events = []
        for result in (2, 2, 2, 2, 0, 0):
            state, event = module.transition(state, result, 3)
            events.append(event)
        self.assertEqual(events, ["PENDING", "PENDING", "ALERT", "ALERT_ACTIVE", "RECOVERED", "OK"])

    def test_unknown_is_not_treated_as_healthy(self):
        state, event = module.transition({}, 3, 1)
        self.assertEqual(event, "ALERT")
        self.assertTrue(state["active"])

    def test_bad_probe_exit_is_not_success(self):
        _, event = module.transition({}, 124, 1)
        self.assertEqual(event, "ALERT")

    def test_transition_and_outbox_are_persisted_together(self):
        import json
        import subprocess
        import sys
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            probe = root / "failed.sh"
            probe.write_text("#!/bin/sh\\nexit 2\\n")
            state = root / "health.json"
            for _ in range(3):
                run = subprocess.run(
                    [sys.executable, str(path), "--state-file", str(state),
                     "--probe", str(probe), "--threshold", "3"],
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(run.returncode, 0, run.stderr)
            stored = json.loads(state.read_text())
            self.assertTrue(stored["active"])
            self.assertEqual(stored["pending_notifications"], ["ALERT"])
            # No duplicate event while failure persists.
            subprocess.run(
                [sys.executable, str(path), "--state-file", str(state),
                 "--probe", str(probe), "--threshold", "3"],
                check=True, capture_output=True, timeout=10,
            )
            self.assertEqual(json.loads(state.read_text())["pending_notifications"], ["ALERT"])


if __name__ == "__main__":
    unittest.main()
