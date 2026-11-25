#!/usr/bin/env python3
"""Compare MineFleet catalogs produced by staging-reset-catalog.sql (#532).

Rules enforced on a reset candidate (a brand-new database built by Alembic):

* schema identical to the running staging database: extensions, roles, schemas, tables,
  columns, constraints, indexes, triggers, RLS flags and policies, grants, sequences,
  functions and views (audit_event monthly partitions excepted, see below);
* the nine reference tables identical, row for row, to the running database;
* audit_event keeps its DEFAULT partition and a partition for the current UTC month;
* no business data: every row of a tenant-scoped table belongs to the platform tenant, the
  only non-empty tables without tenant_id are the reference tables, and before bootstrap the
  tenant table holds the platform tenant only.

Only metadata, counts and digests are read; no row content is ever printed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PLATFORM_TENANT_ID = "00000000-0000-4000-8000-000000000001"
REFERENCE_TABLES = (
    "alembic_version",
    "spatial_ref_sys",
    "license_category_ref",
    "role",
    "role_allowed_scope",
    "saas_plan",
    "vehicle_category_template",
    "vehicle_category_document_template",
    "vehicle_category_template_license",
)
SCHEMA_KINDS = ("ext", "role", "schema", "rel", "col", "con", "idx", "trg", "pol", "seq", "fn", "view")
# Tables without tenant_id that may legitimately hold rows after the platform bootstrap:
# rate-limit buckets are technical counters keyed by HMAC, never business data.
TECHNICAL_TABLES = {"app.auth_failure_bucket"}


class CatalogError(ValueError):
    pass


def parse(text: str) -> dict[str, dict[str, str]]:
    catalog: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 2)
        if len(parts) != 3:
            raise CatalogError(f"malformed catalog line for kind {parts[0]!r}")
        kind, key, value = parts
        bucket = catalog.setdefault(kind, {})
        if key in bucket:
            raise CatalogError(f"duplicate catalog key {kind}|{key}")
        bucket[key] = value
    for required in ("rel", "rows", "ref", "platform_tenant"):
        if not catalog.get(required):
            raise CatalogError(f"catalog has no {required} section (incomplete extraction)")
    return catalog


def load(path: Path) -> dict[str, dict[str, str]]:
    return parse(path.read_text(encoding="utf-8"))


def schema_differences(live: dict, candidate: dict) -> list[str]:
    problems = []
    for kind in SCHEMA_KINDS:
        left, right = live.get(kind, {}), candidate.get(kind, {})
        for key in sorted(left.keys() - right.keys()):
            problems.append(f"schema: {kind} {key} missing from candidate")
        for key in sorted(right.keys() - left.keys()):
            problems.append(f"schema: {kind} {key} only in candidate")
        for key in sorted(left.keys() & right.keys()):
            if left[key] != right[key]:
                problems.append(f"schema: {kind} {key} differs")
    return problems


def partition_problems(candidate: dict, now: datetime) -> list[str]:
    partitions = candidate.get("partition", {})
    current = f"public.audit_event_y{now:%Y}m{now:%m}"
    problems = []
    if "public.audit_event_default" not in partitions:
        problems.append("partition: audit_event DEFAULT partition missing")
    if current not in partitions:
        problems.append(f"partition: {current} (current month) missing")
    for name, value in partitions.items():
        if "rls=true,force=true" not in value.lower():
            problems.append(f"partition: {name} without forced RLS")
    return problems


def reference_differences(live: dict, candidate: dict) -> list[str]:
    return [
        table
        for table in REFERENCE_TABLES
        if live["ref"].get(table) is None or live["ref"].get(table) != candidate["ref"].get(table)
    ]


def data_problems(candidate: dict, phase: str) -> list[str]:
    problems = []
    tenant_tables = set(candidate.get("foreign_tenant_rows", {}))
    for table, count in sorted(candidate.get("foreign_tenant_rows", {}).items()):
        if int(count) != 0:
            problems.append(f"data: {table} holds {count} row(s) of a non-platform tenant")
    references = {f"public.{name}" for name in REFERENCE_TABLES}
    for table, count in sorted(candidate["rows"].items()):
        if int(count) == 0 or table in references or table in tenant_tables:
            continue
        if phase == "bootstrapped" and table in TECHNICAL_TABLES:
            continue
        problems.append(f"data: {table} is not empty ({count} row(s)) and is not a reference table")
    if phase == "fresh":
        allowed_empty_after_build = {"public.tenant"}
        for table, count in sorted(candidate["rows"].items()):
            if table in tenant_tables and table not in allowed_empty_after_build and int(count) != 0:
                problems.append(f"data: {table} must be empty before bootstrap ({count} row(s))")
        if candidate["rows"].get("public.tenant") != "1":
            problems.append("data: tenant must hold exactly the platform tenant before bootstrap")
    platform = candidate.get("platform_tenant", {}).get(PLATFORM_TENANT_ID, "")
    if not platform.endswith(",PLATFORM,ACTIVE"):
        problems.append("data: platform tenant missing or not ACTIVE")
    return problems


def compare(live: dict, candidate: dict, phase: str, now: datetime) -> dict:
    refs = reference_differences(live, candidate)
    report = {
        "phase": phase,
        "schema": schema_differences(live, candidate),
        "partitions": partition_problems(candidate, now),
        "reference_tables_differing": refs,
        "data": data_problems(candidate, phase),
        "counts": {
            "tables": len(candidate["rows"]),
            "partitions": len(candidate.get("partition", {})),
            "triggers": len(candidate.get("trg", {})),
            "policies": len(candidate.get("pol", {})),
            "foreign_keys": sum(1 for v in candidate.get("con", {}).values() if v.startswith("FOREIGN KEY")),
            "non_empty_tables": sorted(t for t, n in candidate["rows"].items() if int(n)),
        },
    }
    report["ok"] = not (report["schema"] or report["partitions"] or refs or report["data"])
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    cmp_parser = sub.add_parser("compare")
    cmp_parser.add_argument("--live", type=Path, required=True)
    cmp_parser.add_argument("--candidate", type=Path, required=True)
    cmp_parser.add_argument("--phase", choices=("fresh", "bootstrapped"), required=True)
    cmp_parser.add_argument("--report", type=Path, required=True)
    refs = sub.add_parser("differing-references")
    refs.add_argument("--live", type=Path, required=True)
    refs.add_argument("--candidate", type=Path, required=True)
    same = sub.add_parser("same-state")
    same.add_argument("before", type=Path)
    same.add_argument("after", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "differing-references":
            print(" ".join(reference_differences(load(args.live), load(args.candidate))))
            return 0
        if args.command == "same-state":
            # Rollback proof: schema, references and exact row counts back to the pre-cutover state.
            before, after = load(args.before), load(args.after)
            problems = schema_differences(before, after) + [
                f"reference {t} differs" for t in reference_differences(before, after)
            ]
            for kind in ("rows", "partition"):
                if before.get(kind) != after.get(kind):
                    problems.append(f"{kind} differ from the pre-cutover state")
            for problem in problems:
                print(f"FAIL: {problem}", file=sys.stderr)
            if not problems:
                print("OK: database identical to the pre-cutover state (schema, references, row counts)")
            return 1 if problems else 0
        report = compare(load(args.live), load(args.candidate), args.phase, datetime.now(UTC))
    except (CatalogError, OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 2
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for section in ("schema", "partitions", "data"):
        for problem in report[section]:
            print(f"FAIL: {problem}", file=sys.stderr)
    for table in report["reference_tables_differing"]:
        print(f"FAIL: reference table {table} differs from the running database", file=sys.stderr)
    if report["ok"]:
        counts = report["counts"]
        print(
            f"OK: candidate ({args.phase}) matches the running schema and the 9 reference tables; "
            f"{counts['tables']} tables, {counts['partitions']} partitions, {counts['triggers']} triggers, "
            f"{counts['policies']} policies, {counts['foreign_keys']} foreign keys; no business data"
        )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
