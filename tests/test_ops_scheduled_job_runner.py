"""Scheduled-job runner and systemd units must use the DEPLOYED API image, never build one.

Regression (staging 2026-11-16): `docker compose run --rm api ...` without the release environment
fell back to MF_API_IMAGE=minefleet-api:local and compose built an image from the sources.
No Docker or systemd required: docker is faked, release_manifest.py is the real validator.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "infra/deploy"
RUNNER = DEPLOY / "run-scheduled-job.sh"
SYSTEMD = DEPLOY / "systemd"
API_IMAGE = f"ghcr.io/skaba89/minefleet360/api@sha256:{'a' * 64}"


def receipt() -> dict[str, object]:
    return {
        "schema_version": 1,
        "environment": "staging",
        "deployment_variant": "edge",
        "release_commit": "1" * 40,
        "migration_head": "0067",
        "api_image": API_IMAGE,
        "web_image": f"ghcr.io/skaba89/minefleet360/web@sha256:{'b' * 64}",
        "created_at": "2026-11-16T12:00:00Z",
        "created_by": "runner-test",
        "rollback": {
            "release_commit": "2" * 40,
            "api_image": f"ghcr.io/skaba89/minefleet360/api@sha256:{'c' * 64}",
            "web_image": f"ghcr.io/skaba89/minefleet360/web@sha256:{'d' * 64}",
            "database_strategy": "application-only-forward-schema",
        },
    }


class ScheduledJobRunnerTests(unittest.TestCase):
    def run_job(
        self,
        job: str,
        *,
        with_receipt: bool = True,
        receipt_value: object | None = None,
        image_present: bool = True,
    ) -> tuple[subprocess.CompletedProcess[str], str, str]:
        with tempfile.TemporaryDirectory() as root:
            temporary = Path(root)
            state = temporary / "release-state"
            state.mkdir()
            if with_receipt:
                (state / "current.json").write_text(json.dumps(receipt_value or receipt()))
            secrets = temporary / "staging.env"
            secrets.write_text("MF_ENV=staging\n")
            secrets.chmod(0o600)
            log = temporary / "docker.log"
            env_copy = temporary / "release.env.copy"
            bin_dir = temporary / "bin"
            bin_dir.mkdir()
            docker = bin_dir / "docker"
            # The fake docker records its arguments and a copy of the release env file it received.
            docker.write_text(
                "#!/bin/bash\n"
                f"printf '%s\\n' \"$*\" >> '{log}'\n"
                "prev=''\n"
                "for a in \"$@\"; do\n"
                f"  if [ \"$prev\" = '--env-file' ] && [ \"$a\" != '{secrets}' ]; then cp \"$a\" '{env_copy}'; fi\n"
                "  prev=\"$a\"\n"
                "done\n"
                f"if [ \"$1 $2\" = 'image inspect' ]; then exit {0 if image_present else 1}; fi\n"
                "exit 0\n"
            )
            docker.chmod(0o700)
            env = {
                **os.environ,
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "MF_RELEASE_STATE_DIR": str(state),
                "MF_STAGING_SECRETS_FILE": str(secrets),
            }
            result = subprocess.run(
                ["bash", str(RUNNER), job],
                check=False,
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
            )
            docker_log = log.read_text() if log.exists() else ""
            release_env = env_copy.read_text() if env_copy.exists() else ""
            return result, docker_log, release_env

    def test_job_runs_deployed_image_without_build(self) -> None:
        result, docker_log, release_env = self.run_job("send-hse-digest")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = docker_log.splitlines()
        self.assertEqual(lines[0], f"image inspect {API_IMAGE}")
        self.assertIn("run --rm --no-deps api minefleet send-hse-digest", lines[1])
        self.assertIn(f"MF_API_IMAGE={API_IMAGE}", release_env)
        self.assertNotIn("PASSWORD", release_env)

    def test_absent_deployed_image_refuses_instead_of_building(self) -> None:
        result, docker_log, _ = self.run_job("send-hse-digest", image_present=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("not present locally", result.stderr)
        self.assertNotIn(" run ", f" {docker_log} ")

    @unittest.skipUnless(shutil.which("docker"), "docker absent : contrôle des options réelles impossible")
    def test_compose_run_flags_exist_in_installed_compose(self) -> None:
        # Régression staging 2026-11-16 : `run --no-build` n'existe pas en Compose v5 ; le faux docker
        # des autres tests accepte tout, seul l'aide réelle de compose fait foi.
        helped = subprocess.run(
            ["docker", "compose", "run", "--help"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if helped.returncode != 0:
            self.skipTest("docker compose indisponible")
        body = RUNNER.read_text()
        run_line = next(line for line in body.splitlines() if line.strip().startswith("run --rm"))
        for flag in re.findall(r"(--[a-z][a-z-]+)", run_line):
            with self.subTest(flag=flag):
                self.assertIn(flag, helped.stdout)

    def test_missing_receipt_refuses_before_docker(self) -> None:
        result, docker_log, _ = self.run_job("evaluate-preventive", with_receipt=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("release receipt missing", result.stderr)
        self.assertEqual(docker_log, "")

    def test_invalid_receipt_refuses_before_docker(self) -> None:
        bad = receipt()
        bad["api_image"] = "minefleet-api:local"
        result, docker_log, _ = self.run_job("sweep-gps-signal", receipt_value=bad)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(docker_log, "")

    def test_unknown_job_is_rejected(self) -> None:
        result, docker_log, _ = self.run_job("create-platform-admin")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(docker_log, "")


class SystemdUnitsTests(unittest.TestCase):
    def test_no_unit_runs_compose_without_release_image(self) -> None:
        for unit in sorted(SYSTEMD.glob("*.service")):
            exec_lines = [
                line for line in unit.read_text().splitlines() if line.startswith("ExecStart=")
            ]
            for line in exec_lines:
                with self.subTest(unit=unit.name):
                    self.assertNotIn(" run ", f" {line} ", "compose run must go through the runner")
                    self.assertNotIn(" build", line)

    def test_every_job_unit_records_a_success_marker(self) -> None:
        for name in (
            "minefleet-hse-digest.service",
            "minefleet-preventive-evaluate.service",
            "minefleet-gps-signal-sweep.service",
            "minefleet-notify-deliver.service",
        ):
            with self.subTest(unit=name):
                body = (SYSTEMD / name).read_text()
                self.assertIn("StateDirectory=minefleet-jobs", body)
                self.assertIn(
                    "ExecStartPost=/usr/bin/touch /var/lib/minefleet-jobs/%N.success", body
                )

    def test_ephemeral_jobs_use_the_runner(self) -> None:
        expected = {
            "minefleet-hse-digest.service": "send-hse-digest",
            "minefleet-preventive-evaluate.service": "evaluate-preventive",
            "minefleet-gps-signal-sweep.service": "sweep-gps-signal",
        }
        for name, job in expected.items():
            with self.subTest(unit=name):
                self.assertIn(
                    f"run-scheduled-job.sh {job}", (SYSTEMD / name).read_text()
                )


if __name__ == "__main__":
    unittest.main()
