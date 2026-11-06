#!/usr/bin/env python3
"""Validate immutable MineFleet staging release and rollback manifests."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

MAX_MANIFEST_BYTES = 16 * 1024
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
MIGRATION_RE = re.compile(r"^[0-9a-z][0-9a-z_-]{1,31}$")
IMAGE_RE = re.compile(
    r"^(?=.{1,512}$)[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]{1,5})?"
    r"(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+@sha256:[0-9a-f]{64}$"
)
ROOT_KEYS = {
    "schema_version",
    "environment",
    "deployment_variant",
    "release_commit",
    "migration_head",
    "api_image",
    "web_image",
    "created_at",
    "created_by",
    "rollback",
}
ROLLBACK_KEYS = {
    "release_commit",
    "api_image",
    "web_image",
    "database_strategy",
}


class ManifestError(ValueError):
    """A release manifest is unsafe or ambiguous."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError("duplicate JSON key")
        result[key] = value
    return result


def _exact_keys(value: dict[str, Any], expected: set[str], location: str) -> None:
    missing = expected - value.keys()
    extra = value.keys() - expected
    if missing or extra:
        raise ManifestError(
            f"{location} keys mismatch (missing={sorted(missing)}, extra={sorted(extra)})"
        )


def _required_string(value: Any, field: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ManifestError(f"{field} must be a non-empty canonical string")
    if len(value) > max_length or any(ord(char) < 32 for char in value):
        raise ManifestError(f"{field} is too long or contains control characters")
    return value


def _commit(value: Any, field: str) -> str:
    candidate = _required_string(value, field, max_length=40)
    if not COMMIT_RE.fullmatch(candidate):
        raise ManifestError(f"{field} must be a full lowercase Git commit")
    return candidate


def _image(value: Any, field: str) -> str:
    candidate = _required_string(value, field)
    if not IMAGE_RE.fullmatch(candidate):
        raise ManifestError(f"{field} must be an OCI image pinned by sha256 digest")
    host = candidate.split("/", 1)[0].split(":", 1)
    if len(host) == 2 and not 1 <= int(host[1]) <= 65535:
        raise ManifestError(f"{field} contains an invalid registry port")
    return candidate


def _utc_timestamp(value: Any) -> str:
    candidate = _required_string(value, "created_at", max_length=40)
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise ManifestError("created_at must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ManifestError("created_at must include the UTC offset")
    return candidate


@dataclass(frozen=True)
class RollbackTarget:
    release_commit: str
    api_image: str
    web_image: str
    database_strategy: str


@dataclass(frozen=True)
class ReleaseManifest:
    deployment_variant: str
    release_commit: str
    migration_head: str
    api_image: str
    web_image: str
    created_at: str
    created_by: str
    rollback: RollbackTarget

    def compose_env(self, *, rollback: bool = False) -> str:
        target = self.rollback if rollback else self
        return "\n".join(
            (
                "MF_ENV=staging",
                f"MF_DEPLOYMENT_VARIANT={self.deployment_variant}",
                f"MF_RELEASE_COMMIT={target.release_commit}",
                f"MF_MIGRATION_HEAD={self.migration_head}",
                f"MF_API_IMAGE={target.api_image}",
                f"MF_WEB_IMAGE={target.web_image}",
                "",
            )
        )


def load_manifest(path: Path) -> ReleaseManifest:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ManifestError("manifest is not readable") from error
    if not 0 < len(raw) <= MAX_MANIFEST_BYTES:
        raise ManifestError("manifest is empty or too large")
    try:
        value = json.loads(raw, object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ManifestError("manifest is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ManifestError("manifest root must be an object")
    _exact_keys(value, ROOT_KEYS, "manifest")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ManifestError("schema_version must be integer 1")
    if value["environment"] != "staging":
        raise ManifestError("only the staging environment is accepted")
    variant = value["deployment_variant"]
    if variant not in {"edge", "standalone"}:
        raise ManifestError("deployment_variant must be edge or standalone")

    release_commit = _commit(value["release_commit"], "release_commit")
    migration_head = _required_string(
        value["migration_head"], "migration_head", max_length=32
    )
    if not MIGRATION_RE.fullmatch(migration_head):
        raise ManifestError("migration_head is invalid")
    api_image = _image(value["api_image"], "api_image")
    web_image = _image(value["web_image"], "web_image")

    rollback_value = value["rollback"]
    if not isinstance(rollback_value, dict):
        raise ManifestError("rollback must be an object")
    _exact_keys(rollback_value, ROLLBACK_KEYS, "rollback")
    rollback = RollbackTarget(
        release_commit=_commit(
            rollback_value["release_commit"], "rollback.release_commit"
        ),
        api_image=_image(rollback_value["api_image"], "rollback.api_image"),
        web_image=_image(rollback_value["web_image"], "rollback.web_image"),
        database_strategy=_required_string(
            rollback_value["database_strategy"],
            "rollback.database_strategy",
            max_length=64,
        ),
    )
    if rollback.database_strategy != "application-only-forward-schema":
        raise ManifestError("rollback must keep the migrated schema forward")
    if rollback.release_commit == release_commit:
        raise ManifestError("rollback release must differ from the target release")
    if rollback.api_image == api_image and rollback.web_image == web_image:
        raise ManifestError("rollback images must differ from the target images")

    return ReleaseManifest(
        deployment_variant=variant,
        release_commit=release_commit,
        migration_head=migration_head,
        api_image=api_image,
        web_image=web_image,
        created_at=_utc_timestamp(value["created_at"]),
        created_by=_required_string(value["created_by"], "created_by", max_length=120),
        rollback=rollback,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("validate", "emit-release-env", "emit-rollback-env")
    )
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as error:
        print(f"FAIL: invalid staging release manifest: {error}", file=sys.stderr)
        return 2
    if args.command == "validate":
        print(
            "OK: immutable staging release manifest "
            f"{manifest.release_commit[:12]} migration={manifest.migration_head} "
            f"variant={manifest.deployment_variant}"
        )
    elif args.command == "emit-release-env":
        sys.stdout.write(manifest.compose_env())
    else:
        sys.stdout.write(manifest.compose_env(rollback=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
