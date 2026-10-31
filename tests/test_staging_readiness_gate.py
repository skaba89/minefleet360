"""Staging readiness gate regression tests with fake Docker and curl; no network."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "infra/deploy/check-preproduction.sh"
COMPOSE = ROOT / "infra/deploy/docker-compose.prod.yml"


class StagingReadinessTests(unittest.TestCase):
    def check(self, statuses: str, url: str = "https://staging.example.invalid"):
        with tempfile.TemporaryDirectory() as root:
            bin_dir = Path(root)
            docker = bin_dir / "docker"
            docker.write_text("#!/bin/sh\nexit 0\n")
            docker.chmod(0o700)
            curl = bin_dir / "curl"
            curl.write_text(
                "#!/bin/sh\n"
                "case \"$*\" in\n"
                f"  *'/api/v1/ready'*) printf '%s' '{statuses.split(',')[-1]}' ;;\n"
                f"  *'/api/v1/health'*) printf '%s' '{statuses.split(',')[1]}' ;;\n"
                f"  *) printf '%s' '{statuses.split(',')[0]}' ;;\n"
                "esac\n"
            )
            curl.chmod(0o700)
            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
                   "MINEFLEET_STAGING_URL": url}
            return subprocess.run(["bash", str(SCRIPT), str(COMPOSE), "--live"],
                                  env=env, capture_output=True, text=True, timeout=15)

    def test_all_three_endpoints_required(self):
        self.assertEqual(self.check("200,200,200").returncode, 0)
        self.assertEqual(self.check("200,200,503").returncode, 1)

    def test_insecure_origin_rejected(self):
        self.assertEqual(self.check("200,200,200", "http://staging.example.invalid").returncode, 1)


if __name__ == "__main__":
    unittest.main()
