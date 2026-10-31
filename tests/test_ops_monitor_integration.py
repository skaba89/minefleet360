"""Integration coverage: monitoring transitions, SMTP outages and eventual recovery.

No Docker, live SMTP or network required. Exercises the real orchestrator subprocess.
"""
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "infra" / "deploy"
spec = importlib.util.spec_from_file_location("monitor_runner", SCRIPTS / "run-alert-monitor.py")
assert spec and spec.loader
import sys
sys.path.insert(0, str(SCRIPTS))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class MonitoringIntegrationTests(unittest.TestCase):
    def test_failure_smtp_retry_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_dir = root / "state"
            state_dir.mkdir()
            checks = [2, 2, 2, 0, 0]
            smtp_accepted = []
            real_run = subprocess.run

            def fake_run(args, **kwargs):
                command = " ".join(map(str, args))
                if "alert-state.py" in command:
                    # Actual alert-state code runs, but its probe subprocess is simulated.
                    with patch.object(subprocess, "run", side_effect=lambda *_a, **_k: subprocess.CompletedProcess([], checks.pop(0))) :
                        import runpy
                        original = sys.argv
                        try:
                            sys.argv = list(map(str, args[1:]))
                            with self.assertRaises(SystemExit) as result:
                                runpy.run_path(str(SCRIPTS / "alert-state.py"), run_name="__main__")
                            self.assertEqual(result.exception.code, 0)
                        finally:
                            sys.argv = original
                    return subprocess.CompletedProcess(args, 0)
                if "notify-alert-smtp.py" in command:
                    if not smtp_accepted:
                        smtp_accepted.append("failed once")
                        return subprocess.CompletedProcess(args, 2)
                    smtp_accepted.append(args[-1])
                    return subprocess.CompletedProcess(args, 0)
                return real_run(args, **kwargs)

            with patch.object(runner.subprocess, "run", side_effect=fake_run):
                original = sys.argv
                try:
                    for expected in (0, 0, 2, 0, 0):
                        sys.argv = ["monitor", "--state-dir", str(state_dir), "--threshold", "3"]
                        self.assertEqual(runner.main(), expected)
                finally:
                    sys.argv = original
            self.assertEqual(smtp_accepted, ["failed once", "ALERT", "RECOVERED"])
            self.assertEqual(json.loads((state_dir / "health-state.json").read_text())["pending_notifications"], [])


if __name__ == "__main__":
    unittest.main()
