"""Unit tests for filtering operational alert events."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "infra/deploy/run-alert-monitor.py"
spec = importlib.util.spec_from_file_location("run_alert_monitor", path)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MonitorQueueTests(unittest.TestCase):
    def test_queue_only_new_alert_and_recovery(self):
        queue = ["ALERT"]
        self.assertEqual(module.add_event(queue, "RECOVERED: operational probe exit=0"), ["ALERT", "RECOVERED"])
        self.assertEqual(queue, ["ALERT"])

    def test_ignore_nontransitions_and_invalid_input(self):
        for value in ("PENDING: operational probe exit=2", "ALERT_ACTIVE: operational probe exit=2", "OK", "ALERT_NOW: anything"):
            self.assertEqual(module.add_event([], value), [])

    def test_preserve_fifo_order(self):
        result = module.add_event(["ALERT", "RECOVERED"], "ALERT: operational probe exit=2")
        self.assertEqual(result, ["ALERT", "RECOVERED", "ALERT"])


if __name__ == "__main__":
    unittest.main()
