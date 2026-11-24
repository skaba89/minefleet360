"""Release manifests, runtime guards and staging release/rollback script.

No Docker, registry or network is required: ``docker``, ``cosign``, ``curl`` and the
business smoke are replaced by stateful fakes inside a private copy of infra/deploy.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "infra/deploy"
VALIDATOR = DEPLOY / "release_manifest.py"
GUARD = DEPLOY / "runtime_guard.py"
SCRIPT = DEPLOY / "staging-release.sh"
sys.path.insert(0, str(DEPLOY))
import runtime_guard  # noqa: E402

RELEASE_COMMIT = "1" * 40
ROLLBACK_API_COMMIT = "2" * 40
ROLLBACK_WEB_COMMIT = "3" * 40
API = "ghcr.io/skaba89/minefleet360/api"
WEB = "ghcr.io/skaba89/minefleet360/web"
FALLBACK_API_ID = "sha256:" + "e" * 64
FALLBACK_WEB_ID = "sha256:" + "f" * 64
REVIEW = "0077 additive nullable column, old API uses explicit columns (review #529)"


def manifest(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 2,
        "environment": "staging",
        "deployment_variant": "edge",
        "release_commit": RELEASE_COMMIT,
        "migration_head": "0077",
        "api_image": f"{API}@sha256:{'a' * 64}",
        "web_image": f"{WEB}@sha256:{'b' * 64}",
        "created_at": "2026-11-24T10:00:00Z",
        "created_by": "release-test",
        "rollback": {
            "api": {
                "release_commit": ROLLBACK_API_COMMIT,
                "image": f"{API}@sha256:{'c' * 64}",
                "migration_head": "0076",
            },
            "web": {
                "release_commit": ROLLBACK_WEB_COMMIT,
                "image": f"{WEB}@sha256:{'d' * 64}",
            },
            "database_strategy": "application-only-forward-schema",
            "schema_compatibility_review": REVIEW,
        },
    }
    value.update(overrides)
    return value


def with_rollback(**changes: object) -> dict[str, object]:
    value = manifest()
    rollback = json.loads(json.dumps(value["rollback"]))
    for dotted, new in changes.items():
        target = rollback
        *parents, leaf = dotted.split("__")
        for parent in parents:
            target = target[parent]
        if new is None:
            del target[leaf]
        else:
            target[leaf] = new
    value["rollback"] = rollback
    return value


def fallback_manifest(root: Path, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "kind": "local-fallback-rollback",
        "environment": "staging",
        "deployment_variant": "edge",
        "provenance": "local-archive-unsigned",
        "forward_migration_head": "0077",
        "database_strategy": "application-only-forward-schema",
        "schema_compatibility_review": REVIEW,
        "created_at": "2026-11-24T10:00:00Z",
        "created_by": "release-test",
        "api": {
            "release_commit": ROLLBACK_API_COMMIT,
            "migration_head": "0076",
            "image_id": FALLBACK_API_ID,
            "archive": str(root / "api.tar").replace("\\", "/"),
            "archive_sha256": "0" * 64,
        },
        "web": {
            "release_commit": ROLLBACK_WEB_COMMIT,
            "image_id": FALLBACK_WEB_ID,
            "archive": str(root / "web.tar").replace("\\", "/"),
            "archive_sha256": "0" * 64,
        },
    }
    value.update(overrides)
    return value


def docker_save_archive(path: Path, image_id: str, repo_tags: list[str] | None) -> str:
    """Write a minimal docker-save tarball and return its SHA256."""
    entries = {
        "manifest.json": json.dumps(
            [
                {
                    "Config": f"blobs/sha256/{image_id.split(':', 1)[1]}",
                    "RepoTags": repo_tags,
                    "Layers": [],
                }
            ]
        ).encode(),
        f"blobs/sha256/{image_id.split(':', 1)[1]}": b"{}",
    }
    with tarfile.open(path, "w") as archive:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_validator(value: object, *args: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / "release.json"
        path.write_text(json.dumps(value))
        command = args[0] if args else "validate"
        return subprocess.run(
            [sys.executable, str(VALIDATOR), command, str(path), *args[1:]],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )


class ReleaseManifestTests(unittest.TestCase):
    def test_valid_manifest_emits_distinct_api_and_web_rollback_commits(self) -> None:
        release = run_validator(manifest(), "emit-release-env")
        self.assertEqual(release.returncode, 0, release.stderr)
        self.assertIn(f"MF_API_COMMIT={RELEASE_COMMIT}", release.stdout)
        self.assertIn(f"MF_WEB_COMMIT={RELEASE_COMMIT}", release.stdout)
        self.assertIn("MF_API_MIGRATION_HEAD=0077", release.stdout)
        self.assertNotIn("PASSWORD", release.stdout)
        self.assertNotIn("SECRET", release.stdout)

        rollback = run_validator(manifest(), "emit-rollback-env")
        self.assertEqual(rollback.returncode, 0, rollback.stderr)
        self.assertIn(f"MF_API_COMMIT={ROLLBACK_API_COMMIT}", rollback.stdout)
        self.assertIn(f"MF_WEB_COMMIT={ROLLBACK_WEB_COMMIT}", rollback.stdout)
        self.assertIn("MF_API_MIGRATION_HEAD=0076", rollback.stdout)
        # The forward schema head is kept: a rollback never targets an older schema.
        self.assertIn("MF_MIGRATION_HEAD=0077", rollback.stdout)
        self.assertIn(f"MF_WEB_IMAGE={WEB}@sha256:{'d' * 64}", rollback.stdout)

    def test_invalid_root_manifests_are_rejected(self) -> None:
        cases = {
            "production": manifest(environment="production"),
            "schema v1": manifest(schema_version=1),
            "float version": manifest(schema_version=2.0),
            "mutable tag": manifest(api_image=f"{API}:latest"),
            "foreign registry": manifest(api_image=f"docker.io/skaba89/api@sha256:{'a' * 64}"),
            "web repo for api": manifest(api_image=f"{WEB}@sha256:{'a' * 64}"),
            "unknown key": manifest(unexpected="value"),
            "short commit": manifest(release_commit="1234567"),
            "naive timestamp": manifest(created_at="2026-11-24T10:00:00"),
            "bad variant": manifest(deployment_variant="swarm"),
        }
        for name, value in cases.items():
            with self.subTest(name):
                self.assertEqual(run_validator(value).returncode, 2)

    def test_legacy_v1_receipt_is_readable_only_by_scheduled_jobs(self) -> None:
        legacy = {
            **manifest(schema_version=1),
            "api_image": f"ghcr.io/skaba89/minefleet-api@sha256:{'a' * 64}",
            "rollback": {
                "release_commit": ROLLBACK_API_COMMIT,
                "api_image": f"{API}@sha256:{'c' * 64}",
                "web_image": f"{WEB}@sha256:{'d' * 64}",
                "database_strategy": "application-only-forward-schema",
            },
        }
        receipt = run_validator(legacy, "emit-release-env")
        self.assertEqual(receipt.returncode, 0, receipt.stderr)
        self.assertIn(f"MF_RELEASE_COMMIT={RELEASE_COMMIT}", receipt.stdout)
        self.assertEqual(run_validator(legacy).returncode, 2)
        self.assertEqual(run_validator(legacy, "emit-rollback-env").returncode, 2)
        # The original v1 rules still apply to receipts.
        legacy["rollback"]["release_commit"] = RELEASE_COMMIT  # type: ignore[index]
        self.assertEqual(run_validator(legacy, "emit-release-env").returncode, 2)

    def test_documented_examples_validate(self) -> None:
        for command, name in (
            ("validate", "release-manifest.example.json"),
            ("validate-fallback", "release-fallback.example.json"),
        ):
            result = subprocess.run(
                [sys.executable, str(VALIDATOR), command, str(DEPLOY / name)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, f"{name}: {result.stderr}")

    def test_duplicate_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "release.json"
            path.write_text('{"schema_version":2,"schema_version":2}')
            result = subprocess.run(
                [sys.executable, str(VALIDATOR), "validate", str(path)],
                check=False,
                capture_output=True,
                timeout=10,
            )
        self.assertEqual(result.returncode, 2)

    def test_incomplete_or_unsafe_rollbacks_are_rejected(self) -> None:
        cases = {
            "missing web": with_rollback(web=None),
            "missing api": with_rollback(api=None),
            "missing api migration head": with_rollback(api__migration_head=None),
            "missing review": with_rollback(schema_compatibility_review=None),
            "trivial review": with_rollback(schema_compatibility_review="ok"),
            "downgrade strategy": with_rollback(database_strategy="downgrade"),
            "api commit equals release": with_rollback(api__release_commit=RELEASE_COMMIT),
            "web commit equals release": with_rollback(web__release_commit=RELEASE_COMMIT),
            "web image equals target": with_rollback(web__image=f"{WEB}@sha256:{'b' * 64}"),
            "api image equals target": with_rollback(api__image=f"{API}@sha256:{'a' * 64}"),
            "newer rollback schema": with_rollback(api__migration_head="0078"),
            "unsigned rollback registry": with_rollback(
                web__image=f"registry.local/minefleet/web@sha256:{'d' * 64}"
            ),
            "extra rollback key": with_rollback(local_archive="/tmp/web.tar"),
        }
        for name, value in cases.items():
            with self.subTest(name):
                self.assertEqual(run_validator(value).returncode, 2, name)

    def test_distinct_rollback_commits_are_accepted(self) -> None:
        result = run_validator(manifest())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"api={ROLLBACK_API_COMMIT[:12]}", result.stdout)
        self.assertIn(f"web={ROLLBACK_WEB_COMMIT[:12]}", result.stdout)


class FallbackManifestTests(unittest.TestCase):
    def test_valid_fallback_uses_local_namespace_never_a_registry(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            result = run_validator(fallback_manifest(Path(root)), "emit-fallback-env")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            f"MF_API_IMAGE=minefleet-local-fallback/api:{ROLLBACK_API_COMMIT}", result.stdout
        )
        self.assertIn(
            f"MF_WEB_IMAGE=minefleet-local-fallback/web:{ROLLBACK_WEB_COMMIT}", result.stdout
        )
        self.assertNotIn("ghcr.io", result.stdout)

    def test_fallback_cannot_claim_signed_provenance_or_be_mixed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            cases = {
                "signed claim": fallback_manifest(base, provenance="ghcr-signed"),
                "wrong kind": fallback_manifest(base, kind="release"),
                "release manifest given": manifest(),
                "relative archive": fallback_manifest(
                    base,
                    api={**fallback_manifest(base)["api"], "archive": "api.tar"},  # type: ignore[dict-item]
                ),
                "dot-dot archive": fallback_manifest(
                    base,
                    web={**fallback_manifest(base)["web"], "archive": "/opt/../etc/web.tar"},  # type: ignore[dict-item]
                ),
                "same image twice": fallback_manifest(
                    base,
                    web={**fallback_manifest(base)["web"], "image_id": FALLBACK_API_ID},  # type: ignore[dict-item]
                ),
                "missing web": {
                    k: v for k, v in fallback_manifest(base).items() if k != "web"
                },
                "downgrade": fallback_manifest(base, database_strategy="downgrade"),
            }
            for name, value in cases.items():
                with self.subTest(name):
                    self.assertEqual(run_validator(value, "validate-fallback").returncode, 2)
            # A fallback manifest is never accepted on the signed path.
            self.assertEqual(run_validator(fallback_manifest(base)).returncode, 2)

    def test_archive_hash_image_id_and_registry_tags_are_checked(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            api_sha = docker_save_archive(base / "api.tar", FALLBACK_API_ID, None)
            web_sha = docker_save_archive(
                base / "web.tar", FALLBACK_WEB_ID, ["ghcr.io/skaba89/minefleet360/web:old"]
            )
            value = fallback_manifest(base)
            value["api"]["archive_sha256"] = api_sha  # type: ignore[index]
            value["web"]["archive_sha256"] = web_sha  # type: ignore[index]
            path = base / "fallback.json"
            path.write_text(json.dumps(value))

            def check(component: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [sys.executable, str(VALIDATOR), "check-archive", str(path), component],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

            api = check("api")
            self.assertEqual(api.returncode, 0, api.stderr)
            self.assertIn("REGISTRY_TAGS=no", api.stdout)
            self.assertIn("REGISTRY_TAGS=yes", check("web").stdout)

            value["api"]["archive_sha256"] = "9" * 64  # type: ignore[index]
            path.write_text(json.dumps(value))
            self.assertEqual(check("api").returncode, 2)

            value["api"]["archive_sha256"] = api_sha  # type: ignore[index]
            value["api"]["image_id"] = "sha256:" + "7" * 64  # type: ignore[index]
            path.write_text(json.dumps(value))
            self.assertEqual(check("api").returncode, 2)


def app_container(service: str, basemap: str, *, port: str = "8200") -> dict[str, object]:
    labels = {"com.docker.compose.project": "minefleet", "com.docker.compose.service": service}
    if service == "api":
        return {
            "Config": {"Labels": labels},
            "Mounts": [
                {
                    "Type": "volume",
                    "Name": "minefleet_mail-capture",
                    "Destination": "/data/mail",
                    "RW": True,
                }
            ],
            "NetworkSettings": {"Networks": {"minefleet_default": {}, "edge": {}}},
            "HostConfig": {
                "PortBindings": {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": port}]},
                "CapDrop": None,
                "SecurityOpt": None,
                "ReadonlyRootfs": False,
            },
        }
    return {
        "Config": {"Labels": labels},
        "Mounts": [
            {"Type": "bind", "Source": basemap, "Destination": "/srv/basemap", "RW": False}
        ],
        "NetworkSettings": {"Networks": {"edge": {}}},
        "HostConfig": {
            "PortBindings": {},
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "ReadonlyRootfs": True,
            "Tmpfs": {"/tmp": ""},
        },
    }


def compose_config(basemap: str) -> dict[str, object]:
    return {
        "name": "minefleet",
        "services": {
            "api": {
                "volumes": [{"type": "volume", "source": "mail-capture", "target": "/data/mail"}],
                "networks": {"default": None, "edge": {"aliases": ["minefleet-api"]}},
                "ports": [
                    {"host_ip": "127.0.0.1", "published": "8200", "target": 8000, "protocol": "tcp"}
                ],
            },
            "web": {
                "volumes": [
                    {"type": "bind", "source": basemap, "target": "/srv/basemap", "read_only": True}
                ],
                "networks": {"edge": {"aliases": ["minefleet-web"]}},
                "read_only": True,
                "tmpfs": ["/tmp"],
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
            },
        },
        "networks": {"default": {"name": "minefleet_default"}, "edge": {"name": "edge"}},
        "volumes": {"mail-capture": {"name": "minefleet_mail-capture"}},
    }


FAKE_DOCKER = r'''#!/usr/bin/env python3
import hashlib, json, os, sys
argv = sys.argv[1:]
root = os.environ["FAKE_ROOT"]
state_path = os.path.join(root, "state.json")
state = json.load(open(state_path))
with open(os.path.join(root, "docker.log"), "a") as log:
    log.write(" ".join(argv) + "\n")
LETTER_COMMIT = {"a": "1" * 40, "b": "1" * 40, "c": "2" * 40, "d": "3" * 40,
                 "e": "2" * 40, "f": "3" * 40}
LETTER_HEAD = {"a": "0077", "c": "0076", "e": "0076"}
def save():
    json.dump(state, open(state_path, "w"))
def image_id(ref):
    ref = state["tags"].get(ref, ref)
    if ref.startswith("sha256:"):
        return ref
    if "@sha256:" in ref:
        return "sha256:" + ref.split("@sha256:")[1][0] * 64
    return None
def letter(ref):
    identifier = image_id(ref)
    return identifier[7] if identifier else ""
def fmt(args):
    return args[args.index("--format") + 1] if "--format" in args else None
if argv[0] == "compose":
    rest, env_files, i = [], [], 1
    while i < len(argv):
        if argv[i] in ("-f", "--profile"):
            i += 2
        elif argv[i] == "--env-file":
            env_files.append(argv[i + 1]); i += 2
        else:
            rest.append(argv[i]); i += 1
    joined = " ".join(rest)
    if rest[:2] == ["config", "--format"]:
        print(json.dumps(json.load(open(os.path.join(root, "compose.json")))))
    elif rest[:2] == ["ps", "-q"]:
        print("\n".join({"db": "dbid", "api": "apiid", "web": "webid"}[s] for s in rest[2:]))
    elif "pg_dump" in joined:
        sys.stdout.write("fake-pg-dump")
    elif "psql" in joined:
        print(state["db_revision"])
    elif rest[:1] == ["up"]:
        if "db" in rest or "--no-deps" not in rest:
            state["db_touched"] = True
        env = {}
        for path in env_files:
            for line in open(path):
                key, _, value = line.strip().partition("=")
                env[key] = value
        state["running"] = {"api": image_id(env["MF_API_IMAGE"]), "web": image_id(env["MF_WEB_IMAGE"])}
        if os.environ.get("FAKE_DB_RECREATED_ON_UP"):
            state["db_started"] = "later"
        if os.environ.get("FAKE_DRIFT_ON_UP"):
            state["drift"] = True
        save()
    elif rest[:4] == ["run", "--rm", "--no-deps", "migrate"] and len(rest) == 4:
        state["db_revision"] = "0077"; save()
    sys.exit(0)
if argv[0] == "inspect":
    form = fmt(argv)
    if form == "{{.Image}}":
        print(state["running"]["api" if argv[-1] == "apiid" else "web"]); sys.exit(0)
    if argv[1:] == ["dbid"]:
        print(json.dumps([{
            "Id": "dbid", "Config": {"Labels": {"com.docker.compose.project": "minefleet",
                                                 "com.docker.compose.service": "db"}},
            "State": {"Status": "running", "StartedAt": state["db_started"],
                      "Health": {"Status": os.environ.get("FAKE_DB_HEALTH", "healthy")}},
            "Mounts": [{"Type": "volume", "Name": os.environ.get("FAKE_DB_VOLUME", "minefleet_db-data"),
                        "Destination": "/var/lib/postgresql/data", "RW": True}]}]))
        sys.exit(0)
    apps = json.load(open(os.path.join(root, "apps.json")))
    if state.get("drift"):
        apps[0]["HostConfig"]["PortBindings"]["8000/tcp"][0]["HostPort"] = "8300"
    print(json.dumps(apps)); sys.exit(0)
if argv[:2] == ["image", "inspect"]:
    form, ref = fmt(argv), argv[-1]
    if form is None:
        sys.exit(0 if ref in state["present"] else 1)
    if form == "{{.Id}}":
        print(image_id(ref)); sys.exit(0)
    if "revision" in form:
        print(LETTER_COMMIT.get(letter(ref), "")); sys.exit(0)
    if "alembic-head" in form:
        print(LETTER_HEAD.get(letter(ref), "")); sys.exit(0)
if argv[0] == "load":
    name = os.path.basename(argv[-1])
    state["present"].append("sha256:" + ("e" if name.startswith("api") else "f") * 64); save()
if argv[0] == "tag":
    state["tags"][argv[2]] = argv[1]; save()
sys.exit(0)
'''

FAKE_COSIGN = r'''#!/usr/bin/env python3
import os, sys
with open(os.path.join(os.environ["FAKE_ROOT"], "cosign.log"), "a") as log:
    log.write(" ".join(sys.argv[1:]) + "\n")
unsigned = os.environ.get("FAKE_UNSIGNED", "")
sys.exit(1 if unsigned and unsigned in sys.argv[-1] else 0)
'''

FAKE_CURL = r'''#!/bin/sh
if grep -q 'compose.* up -d' "$FAKE_ROOT/docker.log" 2>/dev/null; then
  n=$(cat "$FAKE_ROOT/curl.count" 2>/dev/null || echo 0)
  if [ "$n" -lt "${FAKE_TRANSIENT:-0}" ]; then
    echo $((n + 1)) > "$FAKE_ROOT/curl.count"
    printf '502'
    exit 0
  fi
fi
printf '200'
'''

FAKE_SMOKE = r'''#!/usr/bin/env python3
import json, os, sys
if sys.argv[1:] == ["--check-credentials"]:
    text = open(os.environ["MF_SMOKE_CREDENTIALS_FILE"]).read()
    sys.exit(0 if "MF_SMOKE_WORKSPACE=" in text else 2)
state = json.load(open(os.path.join(os.environ["FAKE_ROOT"], "state.json")))
with open(os.path.join(os.environ["FAKE_ROOT"], "smoke.log"), "a") as log:
    log.write(state["running"]["api"] + "\n")
if os.environ.get("FAKE_SMOKE_FAIL_ON_RELEASE") and state["running"]["api"] == "sha256:" + "a" * 64:
    print("FAIL: business smoke: GET /api/v1/missions returned HTTP 500", file=sys.stderr)
    sys.exit(1)
print("OK: business smoke (fake)")
'''


class StagingReleaseScriptTests(unittest.TestCase):
    maxDiff = None

    def run_script(
        self,
        action: str,
        *,
        approval: bool = True,
        permissions: int = 0o600,
        secrets_environment: str = "staging",
        fallback: bool = False,
        fallback_registry_tags: bool = False,
        fallback_present: bool = False,
        db_revision: str = "0076",
        planned_basemap: str | None = None,
        extra_env: dict[str, str] | None = None,
        cosign: bool = True,
        smoke_content: str = "MF_SMOKE_WORKSPACE=demo\n",
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            deploy = base / "deploy"
            shutil.copytree(DEPLOY, deploy, ignore=shutil.ignore_patterns("__pycache__"))
            (deploy / "business-smoke.py").write_text(FAKE_SMOKE)
            basemap = base / "basemap"
            basemap.mkdir()
            (basemap / "guinee.pmtiles").write_bytes(b"PMTiles-guinee")
            (basemap / "france.pmtiles").write_bytes(b"PMTiles-france")
            basemap_text = str(basemap).replace("\\", "/")
            (base / "apps.json").write_text(
                json.dumps([app_container("api", basemap_text), app_container("web", basemap_text)])
            )
            (base / "compose.json").write_text(
                json.dumps(compose_config(planned_basemap or basemap_text))
            )
            present = [FALLBACK_API_ID, FALLBACK_WEB_ID] if fallback_present else []
            (base / "state.json").write_text(
                json.dumps(
                    {
                        "db_revision": db_revision,
                        "db_started": "t0",
                        "running": {"api": "sha256:old-api", "web": "sha256:old-web"},
                        "tags": {},
                        "present": present,
                    }
                )
            )
            if fallback:
                value = fallback_manifest(base)
                tags = ["ghcr.io/skaba89/minefleet360/web:old"] if fallback_registry_tags else None
                value["api"]["archive_sha256"] = docker_save_archive(  # type: ignore[index]
                    base / "api.tar", FALLBACK_API_ID, None
                )
                value["web"]["archive_sha256"] = docker_save_archive(  # type: ignore[index]
                    base / "web.tar", FALLBACK_WEB_ID, tags
                )
            else:
                value = manifest()
            manifest_path = base / "release.json"
            manifest_path.write_text(json.dumps(value))
            secrets = base / "staging.env"
            secrets.write_text(f"MF_ENV={secrets_environment}\nTEST_ONLY_PLACEHOLDER=value\n")
            secrets.chmod(permissions)
            smoke = base / "smoke.env"
            smoke.write_text(smoke_content)
            smoke.chmod(0o600)
            backups = base / "backups"
            backups.mkdir()
            for day in range(1, 11):
                (backups / f"minefleet-202611{day:02d}T000000Z.dump").write_text("old")
            bin_dir = base / "bin"
            bin_dir.mkdir()
            fakes = {"docker": FAKE_DOCKER, "curl": FAKE_CURL}
            if cosign:
                fakes["cosign"] = FAKE_COSIGN
            for name, body in fakes.items():
                (bin_dir / name).write_text(body)
                (bin_dir / name).chmod(0o700)
            path_entries = [str(bin_dir)] + [
                entry
                for entry in os.environ["PATH"].split(os.pathsep)
                if cosign or not (Path(entry) / "cosign").exists()
            ]
            env = {
                **os.environ,
                "PATH": os.pathsep.join(path_entries),
                "FAKE_ROOT": str(base),
                "MF_STAGING_SECRETS_FILE": str(secrets),
                "MINEFLEET_STAGING_URL": "https://staging.example.invalid",
                "MF_BACKUP_DIR": str(backups),
                "MF_RELEASE_STATE_DIR": str(base / "release-state"),
                "MF_RELEASE_READY_TIMEOUT": "5",
                "MF_RELEASE_READY_INTERVAL": "0",
                "MF_SMOKE_CREDENTIALS_FILE": str(smoke),
                **(extra_env or {}),
            }
            if approval:
                if fallback:
                    env["MF_STAGING_CHANGE_APPROVAL"] = (
                        f"{action}:{ROLLBACK_API_COMMIT}:{ROLLBACK_WEB_COMMIT}"
                    )
                else:
                    env["MF_STAGING_CHANGE_APPROVAL"] = f"{action}:{RELEASE_COMMIT}"
            result = subprocess.run(
                ["bash", str(deploy / "staging-release.sh"), action, str(manifest_path)],
                check=False,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            outputs = {
                name: (base / name).read_text() if (base / name).exists() else ""
                for name in ("docker.log", "cosign.log", "smoke.log")
            }
            outputs["state"] = (base / "state.json").read_text()
            outputs["backups"] = "\n".join(sorted(p.name for p in backups.iterdir()))
            return result, outputs

    def assert_postgres_never_touched(self, docker_log: str, state: str) -> None:
        self.assertNotIn('"db_touched": true', state)
        for line in docker_log.splitlines():
            words = line.split()
            if "compose" in words and "up" in words:
                self.assertIn("--no-deps", words, line)
                self.assertNotIn("db", words[words.index("up") :], line)
            for forbidden in ("down", "prune", "rm", "stop", "restart", "kill", "downgrade"):
                self.assertNotIn(forbidden, words, line)

    def test_plan_is_read_only_and_verifies_every_signed_image(self) -> None:
        result, out = self.run_script("plan", approval=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PLAN ONLY", result.stdout)
        self.assertIn("PostgreSQL", result.stdout)
        self.assertIn("france.pmtiles", result.stdout)
        for letter in "abcd":
            self.assertEqual(out["cosign.log"].count(f"sha256:{letter * 64}"), 2, letter)
        self.assertIn("verify-attestation --type https://slsa.dev/provenance/v1", out["cosign.log"])
        for verb in (" pull ", " up ", " run ", "pg_dump", "load ", "tag "):
            self.assertNotIn(verb, f" {out['docker.log']} ")

    def test_unsigned_rollback_image_blocks_the_release_before_any_mutation(self) -> None:
        result, out = self.run_script("apply", extra_env={"FAKE_UNSIGNED": "d" * 64})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cosign signature not verified", result.stderr)
        self.assertNotIn("pg_dump", out["docker.log"])
        self.assertNotIn(" up ", f" {out['docker.log']} ")

    def test_signed_path_requires_cosign(self) -> None:
        if shutil.which("cosign"):
            self.skipTest("a real cosign binary is installed on this host")
        result, out = self.run_script("plan", approval=False, cosign=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("required command missing: cosign", result.stderr)
        self.assertEqual(out["docker.log"], "")

    def test_restricted_secret_file_and_staging_only(self) -> None:
        unsafe, out = self.run_script("plan", approval=False, permissions=0o644)
        self.assertEqual(unsafe.returncode, 2)
        self.assertEqual(out["docker.log"], "")
        prod, out = self.run_script("plan", approval=False, secrets_environment="production")
        self.assertEqual(prod.returncode, 2)
        self.assertEqual(out["docker.log"], "")

    def test_mutation_requires_release_specific_approval(self) -> None:
        result, out = self.run_script("rollback", approval=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("MF_STAGING_CHANGE_APPROVAL", result.stderr)
        self.assertNotIn(" pull ", f" {out['docker.log']} ")

    def test_unhealthy_or_foreign_database_is_refused_before_backup(self) -> None:
        for extra in ({"FAKE_DB_HEALTH": "starting"}, {"FAKE_DB_VOLUME": "other_db-data"}):
            with self.subTest(extra):
                result, out = self.run_script("apply", extra_env=extra)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("pg_dump", out["docker.log"])
                self.assertNotIn(" up ", f" {out['docker.log']} ")

    def test_planned_runtime_drift_is_refused(self) -> None:
        # e.g. the script is run from another checkout: the basemap bind would change.
        result, out = self.run_script("plan", approval=False, planned_basemap="/elsewhere/basemap")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("runtime drift web.mounts", result.stderr)

    def test_apply_backs_up_migrates_and_replaces_only_apps(self) -> None:
        result, out = self.run_script("apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        log = out["docker.log"]
        self.assertLess(log.index("pg_dump"), log.index("pull api migrate web"))
        # Rollback images are fetched and verified before the schema moves forward.
        self.assertLess(log.index("pull api web"), log.index("run --rm --no-deps migrate"))
        self.assertIn("check_schema_revision", log)
        self.assertIn("up -d --no-deps --no-build --pull never api web", log)
        self.assertIn('"db_revision": "0077"', out["state"])
        self.assertIn(f'"api": "sha256:{"a" * 64}"', out["state"])
        self.assertIn("OK: business smoke", result.stdout)
        self.assertIn("PostgreSQL untouched", result.stdout)
        self.assertIn("RELEASE OK", result.stdout)
        self.assert_postgres_never_touched(log, out["state"])

    def test_incomplete_smoke_credentials_block_before_any_mutation(self) -> None:
        for action in ("apply", "rollback"):
            with self.subTest(action):
                result, out = self.run_script(action, db_revision="0077", smoke_content="")
                self.assertEqual(result.returncode, 2)
                for verb in (" pull ", " up ", "pg_dump"):
                    self.assertNotIn(verb, f" {out['docker.log']} ")

    def test_apply_runs_business_smoke_on_running_version_before_backup(self) -> None:
        result, out = self.run_script("apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(out["smoke.log"].splitlines()[0], "sha256:old-api")

    def test_release_never_deletes_existing_backups(self) -> None:
        result, out = self.run_script("apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        for day in range(1, 11):
            self.assertIn(f"minefleet-202611{day:02d}T000000Z.dump", out["backups"])

    def test_business_failure_triggers_rollback_to_distinct_api_and_web(self) -> None:
        result, out = self.run_script("apply", extra_env={"FAKE_SMOKE_FAIL_ON_RELEASE": "1"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("GET /api/v1/missions returned HTTP 500", result.stderr)
        self.assertIn("ROLLBACK OK", result.stderr)
        self.assertIn(f'"api": "sha256:{"c" * 64}"', out["state"])
        self.assertIn(f'"web": "sha256:{"d" * 64}"', out["state"])
        # Schema stays forward: no downgrade after the automatic rollback.
        self.assertIn('"db_revision": "0077"', out["state"])
        self.assertEqual(out["smoke.log"].splitlines()[-1], "sha256:" + "c" * 64)
        self.assert_postgres_never_touched(out["docker.log"], out["state"])

    def test_apply_waits_for_api_readiness_after_restart(self) -> None:
        result, out = self.run_script("apply", extra_env={"FAKE_TRANSIENT": "3"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK: API ready after restart", result.stdout)
        self.assertEqual(out["docker.log"].count("up -d --no-deps"), 1)

    def test_apply_rolls_back_when_api_never_becomes_ready(self) -> None:
        result, out = self.run_script(
            "apply", extra_env={"FAKE_TRANSIENT": "100000", "MF_RELEASE_READY_TIMEOUT": "1"}
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("API not ready within 1s", result.stderr)
        self.assertNotIn("RELEASE OK", result.stdout)

    def test_recreated_postgres_is_detected(self) -> None:
        result, _ = self.run_script("apply", extra_env={"FAKE_DB_RECREATED_ON_UP": "1"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("CRITICAL: PostgreSQL container was recreated or restarted", result.stderr)
        self.assertNotIn("RELEASE OK", result.stdout)

    def test_runtime_drift_after_replacement_is_detected(self) -> None:
        result, _ = self.run_script("rollback", db_revision="0077", extra_env={"FAKE_DRIFT_ON_UP": "1"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("runtime drift api.ports", result.stderr)

    def test_signed_rollback_keeps_schema_and_checks_each_component_commit(self) -> None:
        result, out = self.run_script("rollback", db_revision="0077")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pull api web", out["docker.log"])
        self.assertNotIn("migrate", out["docker.log"])
        self.assertIn('"db_revision": "0077"', out["state"])
        self.assertIn(f"api {ROLLBACK_API_COMMIT[:12]}, web {ROLLBACK_WEB_COMMIT[:12]}", result.stdout)
        self.assertIn("database schema was not downgraded", result.stdout)
        self.assert_postgres_never_touched(out["docker.log"], out["state"])

    def test_rollback_refuses_unknown_database_revision(self) -> None:
        result, out = self.run_script("rollback", db_revision="0042")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(" up ", f" {out['docker.log']} ")

    def test_fallback_plan_is_read_only_and_never_calls_cosign(self) -> None:
        result, out = self.run_script("plan-fallback", approval=False, fallback=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("UNSIGNED", result.stdout)
        self.assertEqual(out["cosign.log"], "")
        for verb in (" pull ", " up ", " load ", " tag ", "pg_dump"):
            self.assertNotIn(verb, f" {out['docker.log']} ")

    def test_fallback_rollback_loads_exact_archives_under_local_tags(self) -> None:
        result, out = self.run_script("rollback-fallback", fallback=True, db_revision="0077")
        self.assertEqual(result.returncode, 0, result.stderr)
        log = out["docker.log"]
        self.assertIn("load --input", log)
        self.assertIn(f"tag {FALLBACK_API_ID} minefleet-local-fallback/api:{ROLLBACK_API_COMMIT}", log)
        self.assertNotIn(" pull ", f" {log} ")
        self.assertNotIn("ghcr.io", log)
        self.assertIn(f'"api": "{FALLBACK_API_ID}"', out["state"])
        self.assertIn(f'"web": "{FALLBACK_WEB_ID}"', out["state"])
        self.assertIn("UNSIGNED local fallback images", result.stdout)
        self.assertIn('"db_revision": "0077"', out["state"])
        self.assert_postgres_never_touched(log, out["state"])

    def test_fallback_refuses_to_load_registry_tagged_archive(self) -> None:
        result, out = self.run_script(
            "rollback-fallback", fallback=True, fallback_registry_tags=True, db_revision="0077"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("carries registry tags", result.stderr)
        self.assertNotIn(" up ", f" {out['docker.log']} ")

    def test_fallback_reuses_present_image_without_loading(self) -> None:
        result, out = self.run_script(
            "rollback-fallback",
            fallback=True,
            fallback_registry_tags=True,
            fallback_present=True,
            db_revision="0077",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("load --input", out["docker.log"])

    def test_fallback_approval_names_both_component_commits(self) -> None:
        result, _ = self.run_script("rollback-fallback", fallback=True, approval=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn(
            f"rollback-fallback:{ROLLBACK_API_COMMIT}:{ROLLBACK_WEB_COMMIT}", result.stderr
        )

    def test_script_contains_no_destructive_database_command(self) -> None:
        text = SCRIPT.read_text()
        for forbidden in (
            "compose down",
            " down ",
            "prune",
            "volume rm",
            "up -d db",
            "alembic downgrade",
            "docker rm",
            "docker stop",
        ):
            self.assertFalse(forbidden in text, f"forbidden command in script: {forbidden}")


class RuntimeGuardTests(unittest.TestCase):
    def snapshot(self, **changes: object) -> dict[str, dict[str, object]]:
        api = app_container("api", "/opt/minefleet/infra/deploy/basemap")
        web = app_container("web", "/opt/minefleet/infra/deploy/basemap")
        for key, value in changes.items():
            target = api if key.startswith("api_") else web
            if key.endswith("ports"):
                target["HostConfig"]["PortBindings"] = value  # type: ignore[index]
            elif key.endswith("mounts"):
                target["Mounts"] = value
            elif key.endswith("networks"):
                target["NetworkSettings"] = {"Networks": value}
        return runtime_guard.snapshot([api, web], "minefleet")

    def test_identical_runtime_passes_invariants(self) -> None:
        state = self.snapshot()
        self.assertEqual(runtime_guard.differences(state, state), [])
        self.assertEqual(
            runtime_guard.check_invariants(state, "/opt/minefleet/infra/deploy/basemap"), []
        )

    def test_compose_plan_normalizes_like_running_containers(self) -> None:
        config = compose_config("/opt/minefleet/infra/deploy/basemap")
        planned = {s: runtime_guard.normalize_compose_service(config, s) for s in ("api", "web")}
        self.assertEqual(runtime_guard.differences(self.snapshot(), planned), [])

    def test_lost_volume_network_port_or_writable_basemap_is_detected(self) -> None:
        before = self.snapshot()
        cases = {
            "api.mounts": self.snapshot(api_mounts=[]),
            "api.ports": self.snapshot(api_ports={}),
            "api.networks": self.snapshot(api_networks={"minefleet_default": {}}),
            "web.mounts": self.snapshot(
                web_mounts=[
                    {
                        "Type": "bind",
                        "Source": "/opt/minefleet/infra/deploy/basemap",
                        "Destination": "/srv/basemap",
                        "RW": True,
                    }
                ]
            ),
        }
        for field, after in cases.items():
            with self.subTest(field):
                problems = runtime_guard.differences(before, after) + runtime_guard.check_invariants(
                    after, None
                )
                self.assertTrue(any(p.startswith(field) for p in problems), problems)

    def test_database_must_be_healthy_and_on_expected_volume(self) -> None:
        container = {
            "Id": "x",
            "Config": {"Labels": {"com.docker.compose.project": "minefleet",
                                  "com.docker.compose.service": "db"}},
            "State": {"Status": "running", "StartedAt": "t", "Health": {"Status": "healthy"}},
            "Mounts": [{"Type": "volume", "Name": "minefleet_db-data",
                        "Destination": "/var/lib/postgresql/data"}],
        }
        self.assertEqual(
            runtime_guard.check_database([container], "minefleet", "minefleet_db-data"), ("x", "t")
        )
        with self.assertRaises(runtime_guard.GuardError):
            runtime_guard.check_database([container], "minefleet", "minefleet_other")
        container["State"]["Health"]["Status"] = "unhealthy"  # type: ignore[index]
        with self.assertRaises(runtime_guard.GuardError):
            runtime_guard.check_database([container], "minefleet", "minefleet_db-data")
        with self.assertRaises(runtime_guard.GuardError):
            runtime_guard.check_database([container, container], "minefleet", "minefleet_db-data")


class BusinessSmokeTests(unittest.TestCase):
    def test_totp_matches_rfc6238_vector(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("business_smoke", DEPLOY / "business-smoke.py")
        smoke = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(smoke)  # type: ignore[union-attr]
        self.assertEqual(smoke.totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", now=59), "287082")
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "smoke.env"
            path.write_text("MF_SMOKE_WORKSPACE=w\nMF_SMOKE_EMAIL=e@example.invalid\n")
            path.chmod(0o600)
            with self.assertRaises(smoke.SmokeError):
                smoke.load_credentials(str(path))


if __name__ == "__main__":
    unittest.main()
