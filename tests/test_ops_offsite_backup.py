"""Off-site encryption/transport tests; use only temporary synthetic content."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "infra/deploy"
VALIDATOR = DEPLOY / "offsite_config.py"
UPLOAD = DEPLOY / "upload-offsite-backup.sh"
VERIFY = DEPLOY / "verify-offsite-backup.sh"


@unittest.skipUnless(shutil.which("rclone"), "rclone required")
class OffsiteBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_context = tempfile.TemporaryDirectory()
        self.temporary = Path(self.temporary_context.name)
        self.remote = self.temporary / "remote"
        self.remote.mkdir()
        self.passphrase = self.temporary / "passphrase"
        self.passphrase.write_text("test-only-offsite-passphrase-0123456789abcdef\n")
        self.passphrase.chmod(0o600)
        self.config = self.temporary / "offsite.env"
        self.config.write_text(
            "MF_OFFSITE_REMOTE=ci-local:backup-vault\n"
            f"MF_OFFSITE_PASSPHRASE_FILE={self.passphrase}\n"
            "MF_OFFSITE_RETENTION_DAYS=30\n"
        )
        self.config.chmod(0o600)
        self.rclone_config = self.temporary / "rclone.conf"
        self.rclone_config.write_text(
            f"[ci-local]\ntype = alias\nremote = {self.remote}\n"
        )
        self.rclone_config.chmod(0o600)
        self.gnupg = self.temporary / "gnupg"
        self.gnupg.mkdir(mode=0o700)
        self.bin_dir = self.temporary / "bin"
        self.bin_dir.mkdir()
        fake_gpg = self.bin_dir / "gpg"
        fake_gpg.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "output=''\n"
            "decrypt=0\n"
            "input=''\n"
            "while [[ $# -gt 0 ]]; do\n"
            '  case "$1" in\n'
            '    --output) output="$2"; shift 2 ;;\n'
            "    --passphrase-file|--cipher-algo|--s2k-digest-algo|--compress-algo) shift 2 ;;\n"
            "    --decrypt) decrypt=1; shift ;;\n"
            "    --batch|--yes|--quiet|--no-symkey-cache|--pinentry-mode|loopback|--symmetric) shift ;;\n"
            '    *) input="$1"; shift ;;\n'
            "  esac\n"
            "done\n"
            'if [[ "$decrypt" == 1 ]]; then base64 -d "$input" > "$output"; '
            'else base64 "$input" > "$output"; fi\n'
        )
        fake_gpg.chmod(0o700)
        self.archive = self.temporary / "minefleet-20261106T070000Z.dump"
        self.archive.write_bytes(b"synthetic-postgresql-dump-without-personal-data")
        self.env = {
            **os.environ,
            "MF_OFFSITE_CONFIG_FILE": str(self.config),
            "RCLONE_CONFIG": str(self.rclone_config),
            "GNUPGHOME": str(self.gnupg),
            "MF_OFFSITE_RESTORE_TMPDIR": str(self.temporary),
            "PATH": f"{self.bin_dir}:{os.environ['PATH']}",
        }

    def tearDown(self) -> None:
        self.temporary_context.cleanup()

    def run_command(self, *command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=self.env,
            timeout=30,
        )

    def test_config_parser_rejects_code_unknown_and_duplicate_keys(self) -> None:
        valid = self.run_command(
            "python3", str(VALIDATOR), "validate", str(self.config)
        )
        self.assertEqual(valid.returncode, 0, valid.stderr)

        for invalid_content in (
            self.config.read_text() + "UNEXPECTED=value\n",
            self.config.read_text() + "MF_OFFSITE_RETENTION_DAYS=10\n",
            self.config.read_text().replace(
                "ci-local:backup-vault", "$(touch /tmp/minefleet-config-must-not-run)"
            ),
        ):
            self.config.write_text(invalid_content)
            result = self.run_command(
                "python3", str(VALIDATOR), "validate", str(self.config)
            )
            self.assertEqual(result.returncode, 2)
            self.config.write_text(
                "MF_OFFSITE_REMOTE=ci-local:backup-vault\n"
                f"MF_OFFSITE_PASSPHRASE_FILE={self.passphrase}\n"
                "MF_OFFSITE_RETENTION_DAYS=30\n"
            )

    def test_upload_rejects_unsafe_configuration_and_passphrase_files(self) -> None:
        self.config.chmod(0o644)
        unsafe_config = self.run_command("bash", str(UPLOAD), str(self.archive))
        self.assertNotEqual(unsafe_config.returncode, 0)
        self.assertIn("permissions", unsafe_config.stderr)
        self.config.chmod(0o600)

        self.passphrase.chmod(0o644)
        unsafe_secret = self.run_command("bash", str(UPLOAD), str(self.archive))
        self.assertNotEqual(unsafe_secret.returncode, 0)
        self.assertIn("permissions", unsafe_secret.stderr)

    def test_upload_contains_only_ciphertext_checksum_and_scoped_retention(
        self,
    ) -> None:
        stale = self.remote / "backup-vault/minefleet-20200101T000000Z.dump.gpg"
        stale.parent.mkdir(parents=True)
        stale.write_text("stale")
        stale.with_suffix(stale.suffix + ".sha256").write_text("stale")
        unrelated = stale.parent / "customer-contract.pdf"
        unrelated.write_text("must remain")
        os.utime(stale, (1, 1))
        os.utime(stale.with_suffix(stale.suffix + ".sha256"), (1, 1))
        os.utime(unrelated, (1, 1))

        result = self.run_command("bash", str(UPLOAD), str(self.archive))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OFFSITE_UPLOAD_OK", result.stdout)
        encrypted = stale.parent / f"{self.archive.name}.gpg"
        checksum = stale.parent / f"{self.archive.name}.gpg.sha256"
        self.assertTrue(encrypted.is_file())
        self.assertTrue(checksum.is_file())
        self.assertNotEqual(encrypted.read_bytes(), self.archive.read_bytes())
        self.assertNotIn(self.archive.read_bytes(), encrypted.read_bytes())
        self.assertFalse(stale.exists())
        self.assertTrue(unrelated.exists())

    def test_download_checksum_decrypt_and_restore_verifier_are_chained(self) -> None:
        uploaded = self.run_command("bash", str(UPLOAD), str(self.archive))
        self.assertEqual(uploaded.returncode, 0, uploaded.stderr)

        copied_deploy = self.temporary / "deploy"
        copied_deploy.mkdir()
        for name in (
            "offsite_config.py",
            "offsite-common.sh",
            "verify-offsite-backup.sh",
        ):
            shutil.copy2(DEPLOY / name, copied_deploy / name)
        verifier_log = self.temporary / "verifier.log"
        fake_verifier = copied_deploy / "verify-restore.sh"
        fake_verifier.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'test "$(cat "$1")" = \'synthetic-postgresql-dump-without-personal-data\'\n'
            f"printf '%s' \"$1\" > '{verifier_log}'\n"
        )
        fake_verifier.chmod(0o700)

        object_name = f"{self.archive.name}.gpg"
        restored = self.run_command(
            "bash", str(copied_deploy / "verify-offsite-backup.sh"), object_name
        )
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertIn("OFFSITE_RESTORE_OK", restored.stdout)
        restored_path = Path(verifier_log.read_text())
        self.assertFalse(
            restored_path.exists(), "plaintext must be deleted after verification"
        )

    def test_restore_rejects_path_traversal_before_remote_access(self) -> None:
        result = self.run_command("bash", str(VERIFY), "../../secret.dump.gpg")
        self.assertEqual(result.returncode, 2)
        self.assertIn("canonical", result.stderr)

    def test_restore_rejects_malformed_checksum_before_decryption(self) -> None:
        uploaded = self.run_command("bash", str(UPLOAD), str(self.archive))
        self.assertEqual(uploaded.returncode, 0, uploaded.stderr)
        object_name = f"{self.archive.name}.gpg"
        checksum = self.remote / "backup-vault" / f"{object_name}.sha256"
        checksum.write_text(checksum.read_text() + "unexpected-second-line\n")

        result = self.run_command("bash", str(VERIFY), object_name)
        self.assertEqual(result.returncode, 1)
        self.assertIn("checksum sidecar is malformed", result.stderr)


if __name__ == "__main__":
    unittest.main()
