"""Exercise the scheduled-jobs probe with a fake systemctl (no systemd, no production files)."""

import os
import stat
import subprocess
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "infra/deploy/probe-scheduled-jobs.sh"

FAKE = """#!/usr/bin/env bash
# Fake systemctl: answers from FAKE_<UNIT>_<FIELD> environment variables.
unit=""; field=""
for arg in "$@"; do
  case "$arg" in *.service) unit="${arg%.service}";; esac
done
key="FAKE_$(echo "$unit" | tr 'a-z-' 'A-Z_')"
if [[ "$1" == "is-failed" ]]; then
  failed="${key}_FAILED"; [[ "${!failed:-no}" == "yes" ]] && exit 0 || exit 1
fi
while [[ $# -gt 0 ]]; do [[ "$1" == "-p" ]] && field="$2"; shift; done
var="${key}_$(echo "$field" | tr 'a-z' 'A-Z')"
echo "${!var:-}"
"""


def stamp(hours_ago: float) -> str:
    return datetime.fromtimestamp(time.time() - hours_ago * 3600).strftime("%a %Y-%m-%d %H:%M:%S")


class ScheduledJobsProbeTests(unittest.TestCase):
    def run_probe(self, **fake: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as root:
            tool = Path(root) / "systemctl"
            tool.write_text(FAKE)
            tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
            env = {**os.environ, "PATH": f"{root}:{os.environ['PATH']}", "MF_SCHEDULED_UNITS": "minefleet-job", **fake}
            return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=10)

    def ok(self, **extra: str) -> dict[str, str]:
        return {
            "FAKE_MINEFLEET_JOB_LOADSTATE": "loaded",
            "FAKE_MINEFLEET_JOB_RESULT": "success",
            "FAKE_MINEFLEET_JOB_EXECMAINEXITTIMESTAMP": stamp(2),
            **extra,
        }

    def test_recent_successful_run_passes(self):
        self.assertEqual(self.run_probe(**self.ok()).returncode, 0)

    def test_failed_or_unsuccessful_run_is_critical(self):
        self.assertEqual(self.run_probe(**self.ok(FAKE_MINEFLEET_JOB_FAILED="yes")).returncode, 2)
        self.assertEqual(self.run_probe(**self.ok(FAKE_MINEFLEET_JOB_RESULT="exit-code")).returncode, 2)

    def test_stale_run_is_critical(self):
        self.assertEqual(self.run_probe(**self.ok(FAKE_MINEFLEET_JOB_EXECMAINEXITTIMESTAMP=stamp(30))).returncode, 2)

    def test_not_installed_or_never_run_is_unknown(self):
        self.assertEqual(self.run_probe(**self.ok(FAKE_MINEFLEET_JOB_LOADSTATE="not-found")).returncode, 3)
        self.assertEqual(self.run_probe(**self.ok(FAKE_MINEFLEET_JOB_EXECMAINEXITTIMESTAMP="")).returncode, 3)

    def test_per_unit_max_age(self):
        recent_enough = self.ok(FAKE_MINEFLEET_JOB_EXECMAINEXITTIMESTAMP=stamp(0.5))
        self.assertEqual(self.run_probe(**recent_enough, MF_SCHEDULED_UNITS="minefleet-job:1").returncode, 0)
        too_old = self.ok(FAKE_MINEFLEET_JOB_EXECMAINEXITTIMESTAMP=stamp(2))
        self.assertEqual(self.run_probe(**too_old, MF_SCHEDULED_UNITS="minefleet-job:1").returncode, 2)
        self.assertEqual(self.run_probe(**too_old, MF_SCHEDULED_UNITS="minefleet-job:0").returncode, 3)

    def test_invalid_configuration_is_unknown(self):
        self.assertEqual(self.run_probe(**self.ok(MF_SCHEDULED_MAX_AGE_HOURS="0")).returncode, 3)
        self.assertEqual(self.run_probe(**self.ok(MF_SCHEDULED_UNITS="bad;unit")).returncode, 3)


if __name__ == "__main__":
    unittest.main()
