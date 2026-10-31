"""Exercise the backup freshness probe without Docker or production files."""
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "infra/deploy/probe-backup-freshness.sh"


class BackupFreshnessTests(unittest.TestCase):
    def run_probe(self, directory: Path, max_age: str = "26") -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "MF_BACKUP_DIR": str(directory), "MF_BACKUP_MAX_AGE_HOURS": max_age}
        return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=10)

    def test_recent_archive_passes_with_absolute_path(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            (directory / "minefleet-20261031T120000Z.dump").write_bytes(b"test-only")
            self.assertEqual(self.run_probe(directory).returncode, 0)

    def test_missing_or_empty_archive_fails(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            self.assertEqual(self.run_probe(directory).returncode, 2)
            (directory / "minefleet-empty.dump").touch()
            self.assertEqual(self.run_probe(directory).returncode, 2)

    def test_stale_archive_fails(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            file = directory / "minefleet-stale.dump"
            file.write_bytes(b"test-only")
            timestamp = time.time() - 48 * 3600
            os.utime(file, (timestamp, timestamp))
            self.assertEqual(self.run_probe(directory).returncode, 2)

    def test_invalid_threshold_is_unknown(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(self.run_probe(Path(root), "0").returncode, 3)


if __name__ == "__main__":
    unittest.main()
