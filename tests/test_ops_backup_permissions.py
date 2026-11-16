"""backup.sh directory permissions: never widened, never reset to 700 over an operator's group read.

Regression (staging 2026-11-16, ST-12): backup.sh forced `chmod 700` on every run, removing the
read/traverse access granted to the monitoring account, so the freshness probe went UNKNOWN.
Docker is faked; no database or network involved.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "infra/deploy/backup.sh"


class BackupPermissionTests(unittest.TestCase):
    def run_backup(self, prepare_mode: int | None) -> tuple[subprocess.CompletedProcess[str], Path]:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        deploy = self.root / "deploy"
        deploy.mkdir()
        shutil.copy(BACKUP, deploy / "backup.sh")
        (deploy / ".env.prod").write_text("MF_ENV=staging\n")
        backups = self.root / "backups"
        if prepare_mode is not None:
            backups.mkdir()
            backups.chmod(prepare_mode)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        docker = bin_dir / "docker"
        docker.write_text(
            "#!/bin/sh\n"
            "case \"$*\" in *'pg_dump'*) printf 'fake-dump' ;; esac\n"
            "exit 0\n"
        )
        docker.chmod(0o700)
        env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "MF_BACKUP_DIR": str(backups),
            "MF_OFFSITE_CONFIG_FILE": str(self.root / "absent-offsite.env"),
        }
        result = subprocess.run(
            ["bash", str(deploy / "backup.sh")],
            check=False,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result, backups

    @staticmethod
    def mode(path: Path) -> int:
        return stat.S_IMODE(path.stat().st_mode)

    def test_new_directory_is_owner_only(self) -> None:
        result, backups = self.run_backup(prepare_mode=None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.mode(backups), 0o700)

    def test_operator_group_read_is_preserved(self) -> None:
        result, backups = self.run_backup(prepare_mode=0o750)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.mode(backups), 0o750)

    def test_world_access_and_group_write_are_removed(self) -> None:
        result, backups = self.run_backup(prepare_mode=0o777)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.mode(backups), 0o750)

    def test_archives_stay_owner_only(self) -> None:
        result, backups = self.run_backup(prepare_mode=0o750)
        self.assertEqual(result.returncode, 0, result.stderr)
        dumps = list(backups.glob("minefleet-*.dump"))
        self.assertEqual(len(dumps), 1)
        self.assertEqual(self.mode(dumps[0]), 0o600)


if __name__ == "__main__":
    unittest.main()
