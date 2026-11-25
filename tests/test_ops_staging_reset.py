"""staging-reset (#532): catalog comparison rules and script guards. No Docker or database needed;
the real PostgreSQL/PostGIS cycle is exercised by docs/audit/preuves/staging/RESET_LAB_*.md."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "infra/deploy"
SCRIPT = DEPLOY / "staging-reset.sh"
sys.path.insert(0, str(DEPLOY))
import staging_reset as sr  # noqa: E402

NOW = datetime(2026, 11, 25, 8, 0, tzinfo=UTC)
PLATFORM = sr.PLATFORM_TENANT_ID
REFS = {t: f"{n}:{t[:8]}digest" for n, t in enumerate(sr.REFERENCE_TABLES, start=1)}


def catalog_text(*, rows: dict[str, int] | None = None, foreign: dict[str, int] | None = None,
                 refs: dict[str, str] | None = None, extra: list[str] | None = None,
                 drop: tuple[str, ...] = (), partitions: list[str] | None = None) -> str:
    lines = [
        "ext|postgis|3.4.3",
        "role|mf_app|super=false,bypassrls=false,login=true,inherit=false",
        "rel|public.tenant|kind=r,owner=mf_owner,rls=true,force=true,acl=",
        "rel|public.vehicle|kind=r,owner=mf_owner,rls=true,force=true,acl=",
        "con|public.vehicle.fk_vehicle__tenant|FOREIGN KEY (tenant_id) REFERENCES tenant(tenant_id)",
        "trg|public.audit_event.tg_audit_event_append_only|CREATE TRIGGER ...,enabled=O",
        "pol|public.vehicle.tenant_isolation|ALL,roles=mf_app,permissive=PERMISSIVE,"
        "using=(tenant_id = app.tid()),check=",
        "idx|public.vehicle.pk_vehicle|CREATE UNIQUE INDEX pk_vehicle ON public.vehicle USING btree (vehicle_id)",
        "alembic|head|0076",
        f"platform_tenant|{PLATFORM}|mf-platform,PLATFORM,ACTIVE",
    ]
    for name in partitions if partitions is not None else ["audit_event_default", "audit_event_y2026m11"]:
        lines.append(f"partition|public.{name}|kind=r,owner=mf_owner,rls=true,force=true,acl=")
    counts = {"public.tenant": 1, "public.vehicle": 0, "public.user_account": 0,
              "app.auth_failure_bucket": 0, "public.weird_global": 0}
    counts.update({f"public.{t}": 1 for t in sr.REFERENCE_TABLES})
    counts.update(rows or {})
    lines += [f"rows|{t}|{n}" for t, n in counts.items()]
    tenant_scoped = {"public.tenant": 0, "public.vehicle": 0, "public.user_account": 0}
    tenant_scoped.update(foreign or {})
    lines += [f"foreign_tenant_rows|{t}|{n}" for t, n in tenant_scoped.items()]
    lines += [f"ref|{t}|{d}" for t, d in (refs or REFS).items()]
    lines += extra or []
    return "\n".join(line for line in lines if not line.startswith(drop) or not drop) + "\n"


def cmp(live: str, candidate: str, phase: str = "fresh") -> dict:
    return sr.compare(sr.parse(live), sr.parse(candidate), phase, NOW)


class CatalogComparisonTests(unittest.TestCase):
    def test_identical_fresh_candidate_is_accepted(self) -> None:
        live = catalog_text(rows={"public.vehicle": 48, "public.user_account": 66, "public.tenant": 6},
                            foreign={"public.vehicle": 48, "public.user_account": 65, "public.tenant": 5})
        report = cmp(live, catalog_text())
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["counts"]["foreign_keys"], 1)

    def test_schema_drift_is_refused(self) -> None:
        base = catalog_text()
        cases = {
            "trigger missing": catalog_text(drop=("trg|",)),
            "policy changed": base.replace("using=(tenant_id = app.tid())", "using=true"),
            "rls disabled": base.replace(
                "public.vehicle|kind=r,owner=mf_owner,rls=true", "public.vehicle|kind=r,owner=mf_owner,rls=false"
            ),
            "extra index": catalog_text(extra=["idx|public.vehicle.ix_new|CREATE INDEX ix_new ON public.vehicle (x)"]),
            "role privilege": base.replace("bypassrls=false", "bypassrls=true"),
        }
        for name, candidate in cases.items():
            with self.subTest(name):
                report = cmp(base, candidate)
                self.assertFalse(report["ok"])
                self.assertTrue(report["schema"], name)

    def test_reference_content_must_be_identical(self) -> None:
        changed = dict(REFS, saas_plan="4:otherdigest")
        report = cmp(catalog_text(), catalog_text(refs=changed))
        self.assertFalse(report["ok"])
        self.assertEqual(report["reference_tables_differing"], ["saas_plan"])
        missing = {k: v for k, v in REFS.items() if k != "vehicle_category_template_license"}
        self.assertIn("vehicle_category_template_license",
                      cmp(catalog_text(), catalog_text(refs=missing))["reference_tables_differing"])

    def test_business_data_in_candidate_is_refused(self) -> None:
        cases = {
            "foreign tenant rows": catalog_text(rows={"public.vehicle": 3}, foreign={"public.vehicle": 3}),
            "second tenant": catalog_text(rows={"public.tenant": 2}, foreign={"public.tenant": 1}),
            "user before bootstrap": catalog_text(rows={"public.user_account": 1}),
            "unclassified global table": catalog_text(rows={"public.weird_global": 1}),
            "rate-limit rows before bootstrap": catalog_text(rows={"app.auth_failure_bucket": 1}),
        }
        for name, candidate in cases.items():
            with self.subTest(name):
                report = cmp(catalog_text(), candidate)
                self.assertFalse(report["ok"], name)
                self.assertTrue(report["data"], name)

    def test_bootstrapped_candidate_may_hold_platform_rows_only(self) -> None:
        platform_only = catalog_text(rows={"public.user_account": 1, "app.auth_failure_bucket": 1})
        self.assertTrue(cmp(catalog_text(), platform_only, "bootstrapped")["ok"])
        other_tenant = catalog_text(rows={"public.user_account": 2}, foreign={"public.user_account": 1})
        self.assertFalse(cmp(catalog_text(), other_tenant, "bootstrapped")["ok"])

    def test_platform_tenant_must_survive(self) -> None:
        candidate = catalog_text().replace("mf-platform,PLATFORM,ACTIVE", "mf-platform,PLATFORM,SUSPENDED")
        self.assertIn("data: platform tenant missing or not ACTIVE", cmp(catalog_text(), candidate)["data"])

    def test_audit_partitions(self) -> None:
        self.assertFalse(cmp(catalog_text(), catalog_text(partitions=["audit_event_default"]))["ok"])
        self.assertFalse(cmp(catalog_text(), catalog_text(partitions=["audit_event_y2026m11"]))["ok"])
        unforced = catalog_text().replace(
            "partition|public.audit_event_y2026m11|kind=r,owner=mf_owner,rls=true,force=true",
            "partition|public.audit_event_y2026m11|kind=r,owner=mf_owner,rls=true,force=false")
        self.assertTrue(cmp(catalog_text(), unforced)["partitions"])
        # Older live partitions with another date are reported, never required in the candidate.
        live = catalog_text(partitions=["audit_event_default", "audit_event_y2026m10", "audit_event_y2026m11"])
        self.assertTrue(cmp(live, catalog_text())["ok"])

    def test_incomplete_or_malformed_catalog_is_rejected(self) -> None:
        with self.assertRaises(sr.CatalogError):
            sr.parse("rows|public.tenant|1\n")
        with self.assertRaises(sr.CatalogError):
            sr.parse(catalog_text() + "garbage-without-separators\n")
        with self.assertRaises(sr.CatalogError):
            sr.parse(catalog_text() + "rows|public.tenant|1\n")

    def test_cli_compare_same_state_and_differing_references(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            (base / "live").write_text(catalog_text())
            (base / "cand").write_text(catalog_text(refs=dict(REFS, saas_plan="4:x")))
            run = lambda *a: subprocess.run([sys.executable, str(DEPLOY / "staging_reset.py"), *a],  # noqa: E731
                                            capture_output=True, text=True, timeout=20, check=False)
            refs = run("differing-references", "--live", str(base / "live"), "--candidate", str(base / "cand"))
            self.assertEqual(refs.stdout.strip(), "saas_plan")
            result = run("compare", "--live", str(base / "live"), "--candidate", str(base / "cand"),
                         "--phase", "fresh", "--report", str(base / "r.json"))
            self.assertEqual(result.returncode, 1)
            self.assertFalse(json.loads((base / "r.json").read_text())["ok"])
            self.assertEqual(run("same-state", str(base / "live"), str(base / "live")).returncode, 0)
            (base / "after").write_text(catalog_text(rows={"public.vehicle": 1}))
            self.assertEqual(run("same-state", str(base / "live"), str(base / "after")).returncode, 1)


FAKE_DOCKER = r'''#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(" ".join(argv) + "\n")
joined = " ".join(argv)
if argv[0] == "compose":
    if "config --format json" in joined:
        print(json.dumps({"volumes": {"db-data": {"name": os.environ.get("FAKE_RESOLVED", "x")}}}))
    elif " ps -q db" in " " + joined:
        print("dbid")
    elif " ps -q api" in " " + joined:
        print("apiid")
    sys.exit(0)
if argv[0] == "inspect":
    if "{{.Name}}" in joined:
        print("/minefleet-db-1")
    elif "{{.Config.Image}}" in joined:
        print("ghcr.io/skaba89/minefleet360/api@sha256:" + "3" * 64)
    else:
        print(json.dumps([{"Id": "dbid" + "0" * 60,
            "Config": {"Labels": {"com.docker.compose.project": "minefleet", "com.docker.compose.service": "db"}},
            "State": {"Status": "running", "StartedAt": "t0", "Health": {"Status": "healthy"}},
            "Mounts": [{"Type": "volume", "Name": "minefleet_db-data", "Destination": "/var/lib/postgresql/data"}]}]))
    sys.exit(0)
if argv[0] == "exec":
    sys.stdout.write(open(os.environ["FAKE_CATALOG"]).read())
    sys.exit(0)
if argv[:2] == ["volume", "inspect"]:
    sys.exit(1)
sys.exit(0)
'''


class StagingResetScriptTests(unittest.TestCase):
    def run_script(self, *args: str, env_line: str = "MF_ENV=staging", mode: int = 0o600,
                   host: str | None = "auto", extra: dict[str, str] | None = None
                   ) -> tuple[subprocess.CompletedProcess[str], str, Path]:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        deploy = root / "deploy"
        shutil.copytree(DEPLOY, deploy, ignore=shutil.ignore_patterns("__pycache__", "release-state"))
        secrets = deploy / ".env.prod"
        secrets.write_text(f"{env_line}\nPOSTGRES_PASSWORD=placeholder\n")
        secrets.chmod(mode)
        (root / "catalog").write_text(catalog_text())
        bin_dir = root / "bin"
        bin_dir.mkdir()
        (bin_dir / "docker").write_text(FAKE_DOCKER)
        (bin_dir / "docker").chmod(0o700)
        hostname = subprocess.run(["hostname"], capture_output=True, text=True, check=True).stdout.strip()
        env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
               "FAKE_LOG": str(root / "docker.log"), "FAKE_CATALOG": str(root / "catalog")}
        env.pop("MF_RESET_APPROVAL", None)
        if host == "auto":
            env["MF_RESET_EXPECTED_HOST"] = hostname
        elif host is not None:
            env["MF_RESET_EXPECTED_HOST"] = host
        else:
            env.pop("MF_RESET_EXPECTED_HOST", None)
        env.update(extra or {})
        result = subprocess.run(["bash", str(deploy / "staging-reset.sh"), *args], env=env,
                                capture_output=True, text=True, timeout=60, check=False)
        log = (root / "docker.log").read_text() if (root / "docker.log").exists() else ""
        return result, log, deploy

    def assert_no_mutation(self, log: str) -> None:
        for verb in (" up ", " run ", " stop ", " start ", " cp ", " volume create", "minefleet-reset-"):
            self.assertNotIn(verb, f" {log} ", verb)

    def test_plan_is_the_default_and_read_only(self) -> None:
        result, log, deploy = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PLAN (read-only, nothing changed)", result.stdout)
        self.assertIn("alembic: 0076", result.stdout)
        self.assertIn("MF_RESET_APPROVAL=build-candidate:dbid00000000:minefleet_db-data", result.stdout)
        self.assert_no_mutation(log)
        self.assertFalse((deploy / "release-state").exists())

    def test_production_unidentified_and_unprotected_environments_are_refused(self) -> None:
        cases = {
            "production": dict(env_line="MF_ENV=production"),
            "no MF_ENV": dict(env_line="MF_OTHER=1"),
            "duplicate MF_ENV": dict(env_line="MF_ENV=staging\nMF_ENV=production"),
            "world-readable secrets": dict(mode=0o644),
            "host not confirmed": dict(host=None),
            "other host": dict(host="another-vps"),
        }
        for name, kwargs in cases.items():
            with self.subTest(name):
                result, log, _ = self.run_script("plan", **kwargs)
                self.assertEqual(result.returncode, 2, name)
                self.assertEqual(log, "", name)

    def test_every_mutating_step_requires_its_exact_approval(self) -> None:
        result, log, _ = self.run_script("build-candidate")
        self.assertEqual(result.returncode, 1)
        self.assertIn("MF_RESET_APPROVAL=build-candidate:dbid00000000:minefleet_db-data", result.stderr)
        self.assert_no_mutation(log)
        result, log, _ = self.run_script(
            "build-candidate", extra={"MF_RESET_APPROVAL": "build-candidate:other:minefleet_db-data"})
        self.assertEqual(result.returncode, 1)
        self.assert_no_mutation(log)

    def test_candidate_names_are_strict(self) -> None:
        for name in ("minefleet", "minefleet-reset-x", "../minefleet-reset-20261125t000000z", ""):
            with self.subTest(name):
                result, log, _ = self.run_script("cutover", name)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(log, "")

    def test_candidate_never_starts_on_the_running_volume(self) -> None:
        result, log, _ = self.run_script(
            "build-candidate",
            extra={"MF_RESET_APPROVAL": "build-candidate:dbid00000000:minefleet_db-data",
                   "FAKE_RESOLVED": "minefleet_db-data"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("refusing to start it", result.stderr)
        self.assertNotIn(" up ", f" {log} ")

    def test_unknown_candidate_is_refused_before_any_change(self) -> None:
        result, log, _ = self.run_script(
            "cutover", "minefleet-reset-20261125t000000z",
            extra={"MF_RESET_APPROVAL": "cutover:minefleet-reset-20261125t000000z:dbid00000000"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown candidate", result.stderr)
        self.assert_no_mutation(log)

    def test_no_destructive_command_and_deletes_only_inside_the_candidate(self) -> None:
        text = SCRIPT.read_text()
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        for forbidden in ("DROP DATABASE", "TRUNCATE", "compose down", " down ", "volume rm", "docker rm",
                          "prune", "DISABLE TRIGGER", "DISABLE ROW LEVEL", "session_replication_role",
                          "NO FORCE ROW LEVEL", "alembic downgrade"):
            self.assertNotIn(forbidden, code, forbidden)
        deletes = [line for line in code.splitlines() if "DELETE" in line]
        self.assertEqual(len(deletes), 1)
        self.assertIn("DELETE FROM public.%s", deletes[0])
        self.assertRegex(code, re.compile(r'docker exec -i "\$cand_db" psql[^\n]*-1 < "\$temporary/\$table.sql"'))

    def test_compose_volume_default_is_the_historic_volume(self) -> None:
        compose = (DEPLOY / "docker-compose.prod.yml").read_text()
        self.assertIn("name: ${MF_DB_VOLUME:-minefleet_db-data}", compose)


if __name__ == "__main__":
    unittest.main()
