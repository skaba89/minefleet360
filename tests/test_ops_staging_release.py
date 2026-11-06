"""Release manifest and staging rollback tests; no Docker or network required."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "infra/deploy/release_manifest.py"
SCRIPT = ROOT / "infra/deploy/staging-release.sh"
RELEASE_COMMIT = "1" * 40
ROLLBACK_COMMIT = "2" * 40


def manifest(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "environment": "staging",
        "deployment_variant": "edge",
        "release_commit": RELEASE_COMMIT,
        "migration_head": "0063",
        "api_image": f"ghcr.io/skaba89/minefleet-api@sha256:{'a' * 64}",
        "web_image": f"ghcr.io/skaba89/minefleet-web@sha256:{'b' * 64}",
        "created_at": "2026-11-05T20:00:00Z",
        "created_by": "release-test",
        "rollback": {
            "release_commit": ROLLBACK_COMMIT,
            "api_image": f"ghcr.io/skaba89/minefleet-api@sha256:{'c' * 64}",
            "web_image": f"ghcr.io/skaba89/minefleet-web@sha256:{'d' * 64}",
            "database_strategy": "application-only-forward-schema",
        },
    }
    value.update(overrides)
    return value


class ReleaseManifestTests(unittest.TestCase):
    def run_validator(
        self, value: object, command: str = "validate"
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "release.json"
            path.write_text(json.dumps(value))
            return subprocess.run(
                ["python3", str(VALIDATOR), command, str(path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )

    def test_valid_manifest_emits_only_non_secret_release_values(self) -> None:
        result = self.run_validator(manifest(), "emit-release-env")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MF_ENV=staging", result.stdout)
        self.assertIn(f"MF_RELEASE_COMMIT={RELEASE_COMMIT}", result.stdout)
        self.assertIn("MF_MIGRATION_HEAD=0063", result.stdout)
        self.assertIn("@sha256:", result.stdout)
        self.assertNotIn("PASSWORD", result.stdout)
        self.assertNotIn("SECRET", result.stdout)

    def test_production_and_mutable_images_are_rejected(self) -> None:
        self.assertEqual(
            self.run_validator(manifest(environment="production")).returncode, 2
        )
        self.assertEqual(
            self.run_validator(
                manifest(api_image="ghcr.io/skaba89/minefleet-api:latest")
            ).returncode,
            2,
        )

    def test_unknown_or_duplicate_keys_are_rejected(self) -> None:
        self.assertEqual(self.run_validator(manifest(unexpected="value")).returncode, 2)
        self.assertEqual(self.run_validator(manifest(schema_version=1.0)).returncode, 2)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "release.json"
            path.write_text('{"schema_version":1,"schema_version":1}')
            result = subprocess.run(
                ["python3", str(VALIDATOR), "validate", str(path)],
                check=False,
                capture_output=True,
                timeout=10,
            )
        self.assertEqual(result.returncode, 2)

    def test_rollback_must_be_a_different_forward_schema_release(self) -> None:
        value = manifest()
        rollback = dict(value["rollback"])  # type: ignore[arg-type]
        rollback["release_commit"] = RELEASE_COMMIT
        value["rollback"] = rollback
        self.assertEqual(self.run_validator(value).returncode, 2)
        rollback["release_commit"] = ROLLBACK_COMMIT
        rollback["database_strategy"] = "downgrade"
        self.assertEqual(self.run_validator(value).returncode, 2)


class StagingReleaseScriptTests(unittest.TestCase):
    def run_script(
        self,
        action: str,
        *,
        environment: str = "staging",
        secrets_environment: str = "staging",
        permissions: int = 0o600,
        approval: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], str]:
        with tempfile.TemporaryDirectory() as root:
            temporary = Path(root)
            manifest_path = temporary / "release.json"
            manifest_path.write_text(json.dumps(manifest(environment=environment)))
            secrets = temporary / "staging.env"
            secrets.write_text(
                f"MF_ENV={secrets_environment}\nTEST_ONLY_PLACEHOLDER=value\n"
            )
            secrets.chmod(permissions)
            log = temporary / "docker.log"
            bin_dir = temporary / "bin"
            bin_dir.mkdir()
            docker = bin_dir / "docker"
            docker.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$*\" >> '{log}'\n"
                'case "$*" in\n'
                "  *'pg_dump -U postgres -Fc minefleet'*) printf '%s' 'fake-pg-dump' ;;\n"
                "  *'com.minefleet.alembic-head'*) printf '%s\\n' '0063' ;;\n"
                f"  *'sha256:{'c' * 64}'*|*'sha256:{'d' * 64}'*) printf '%s\\n' '{ROLLBACK_COMMIT}' ;;\n"
                f"  *'sha256:{'a' * 64}'*|*'sha256:{'b' * 64}'*) printf '%s\\n' '{RELEASE_COMMIT}' ;;\n"
                "esac\n"
                "exit 0\n"
            )
            docker.chmod(0o700)
            curl = bin_dir / "curl"
            curl.write_text("#!/bin/sh\nprintf '200'\n")
            curl.chmod(0o700)
            env = {
                **os.environ,
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "MF_STAGING_SECRETS_FILE": str(secrets),
                "MINEFLEET_STAGING_URL": "https://staging.example.invalid",
                "MF_BACKUP_DIR": str(temporary / "backups"),
                "MF_RELEASE_STATE_DIR": str(temporary / "release-state"),
            }
            if approval:
                env["MF_STAGING_CHANGE_APPROVAL"] = f"{action}:{RELEASE_COMMIT}"
            result = subprocess.run(
                ["bash", str(SCRIPT), action, str(manifest_path)],
                check=False,
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
            )
            return result, log.read_text() if log.exists() else ""

    def test_plan_is_read_only_and_accepts_only_restricted_secret_file(self) -> None:
        result, docker_log = self.run_script("plan")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PLAN ONLY", result.stdout)
        self.assertIn("config --quiet", docker_log)
        self.assertNotIn(" up ", f" {docker_log} ")

        unsafe, unsafe_log = self.run_script("plan", permissions=0o644)
        self.assertEqual(unsafe.returncode, 2)
        self.assertEqual(unsafe_log, "")

    def test_mutation_requires_release_specific_approval(self) -> None:
        result, docker_log = self.run_script("rollback")
        self.assertEqual(result.returncode, 2)
        self.assertIn("MF_STAGING_CHANGE_APPROVAL", result.stderr)
        self.assertIn("config --quiet", docker_log)
        self.assertNotIn("pull api web", docker_log)

    def test_rollback_uses_only_previous_app_images_without_migration(self) -> None:
        result, docker_log = self.run_script("rollback", approval=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pull api web", docker_log)
        self.assertIn("up -d --no-build api web", docker_log)
        self.assertNotIn("migrate", docker_log)
        self.assertIn("database schema was not downgraded", result.stdout)

    def test_apply_requires_backup_and_checks_target_image_metadata(self) -> None:
        result, docker_log = self.run_script("apply", approval=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pg_dump -U postgres -Fc minefleet", docker_log)
        self.assertIn("pull api migrate web", docker_log)
        self.assertIn("com.minefleet.alembic-head", docker_log)
        self.assertIn("run --rm --no-deps migrate", docker_log)
        self.assertIn("up -d --no-build api web", docker_log)
        self.assertIn("RELEASE OK", result.stdout)

    def test_production_manifest_is_rejected_before_docker(self) -> None:
        result, docker_log = self.run_script("plan", environment="production")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(docker_log, "")

        result, docker_log = self.run_script("plan", secrets_environment="production")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(docker_log, "")


if __name__ == "__main__":
    unittest.main()
