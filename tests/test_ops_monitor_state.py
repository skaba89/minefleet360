"""Crash-safe operational state tests."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

module_path = Path(__file__).resolve().parents[1] / "infra/deploy/monitor_state.py"
spec = importlib.util.spec_from_file_location("monitor_state", module_path)
assert spec and spec.loader
state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state)


class MonitorStateTests(unittest.TestCase):
    def test_writes_and_preserves_queue(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "health.json"
            state.write_state(file, {"active": True, "pending_notifications": ["ALERT"]})
            self.assertEqual(state.read_state(file)["pending_notifications"], ["ALERT"])
            state.write_state(file, {"active": False, "pending_notifications": ["ALERT", "RECOVERED"]})
            self.assertEqual(state.read_state(file)["pending_notifications"], ["ALERT", "RECOVERED"])
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)

    def test_invalid_state_not_silently_reset(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "health.json"
            file.write_text("{incomplete")
            with self.assertRaises(json.JSONDecodeError):
                state.read_state(file)
            self.assertEqual(file.read_text(), "{incomplete")

    def test_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "health.json"
            target = Path(root) / "target.json"
            target.write_text("{}")
            file.symlink_to(target)
            with self.assertRaises(ValueError):
                state.write_state(file, {})


if __name__ == "__main__":
    unittest.main()
