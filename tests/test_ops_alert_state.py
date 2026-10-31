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

if __name__ == "__main__":
    unittest.main()
