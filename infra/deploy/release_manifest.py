#!/usr/bin/env python3
"""Validate MineFleet staging release manifests.

Two manifest kinds exist and are never mixed:

* ``release`` (schema_version 2): the official path. Every image, target and rollback,
  is a GHCR digest of the signed ``release-images`` workflow; the deployment script
  verifies Cosign signatures and SLSA attestations before any mutation. API and web
  rollback targets carry their own commit because they may come from different builds.
* ``local-fallback-rollback`` (schema_version 1): an emergency path restoring exact
  application images kept as local ``docker save`` archives. These images are unsigned
  local artifacts: they are tagged only under ``minefleet-local-fallback/`` and are never
  described or tagged as GHCR artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

MAX_MANIFEST_BYTES = 16 * 1024
MAX_ARCHIVE_INDEX_BYTES = 1024 * 1024
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
MIGRATION_RE = re.compile(r"^[0-9a-z][0-9a-z_-]{1,31}$")
IMAGE_RE = re.compile(
    r"^(?=.{1,512}$)[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]{1,5})?"
    r"(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+@sha256:[0-9a-f]{64}$"
)
# Only images published by .github/workflows/release-images.yml are accepted on the signed path.
SIGNED_REPOSITORIES = {
    "api": "ghcr.io/skaba89/minefleet360/api",
    "web": "ghcr.io/skaba89/minefleet360/web",
}
LOCAL_FALLBACK_NAMESPACE = "minefleet-local-fallback"
DATABASE_STRATEGY = "application-only-forward-schema"

RELEASE_KEYS = {
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
ROLLBACK_KEYS = {"api", "web", "database_strategy", "schema_compatibility_review"}
ROLLBACK_API_KEYS = {"release_commit", "image", "migration_head"}
ROLLBACK_WEB_KEYS = {"release_commit", "image"}

FALLBACK_KEYS = {
    "schema_version",
    "kind",
    "environment",
    "deployment_variant",
    "provenance",
    "forward_migration_head",
    "database_strategy",
    "schema_compatibility_review",
    "created_at",
    "created_by",
    "api",
    "web",
}
FALLBACK_API_KEYS = {
    "release_commit",
    "migration_head",
    "image_id",
    "archive",
    "archive_sha256",
}
FALLBACK_WEB_KEYS = FALLBACK_API_KEYS - {"migration_head"}


class ManifestError(ValueError):
    """A release manifest is unsafe or ambiguous."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError("duplicate JSON key")
        result[key] = value
    return result


def _exact_keys(value: Any, expected: set[str], location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{location} must be an object")
    missing = expected - value.keys()
    extra = value.keys() - expected
    if missing or extra:
        raise ManifestError(
            f"{location} keys mismatch (missing={sorted(missing)}, extra={sorted(extra)})"
        )
    return value


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


def _migration(value: Any, field: str) -> str:
    candidate = _required_string(value, field, max_length=32)
    if not MIGRATION_RE.fullmatch(candidate):
        raise ManifestError(f"{field} is invalid")
    return candidate


def _signed_image(value: Any, field: str, component: str) -> str:
    candidate = _required_string(value, field)
    if not IMAGE_RE.fullmatch(candidate):
        raise ManifestError(f"{field} must be an OCI image pinned by sha256 digest")
    repository = candidate.split("@", 1)[0]
    if repository != SIGNED_REPOSITORIES[component]:
        raise ManifestError(
            f"{field} must come from the signed repository {SIGNED_REPOSITORIES[component]}"
        )
    return candidate


def _utc_timestamp(value: Any) -> str:
    candidate = _required_string(value, "created_at", max_length=40)
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as error:
        raise ManifestError("created_at must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ManifestError("created_at must include the UTC offset")
    return candidate


def _review(value: Any) -> str:
    review = _required_string(value, "schema_compatibility_review", max_length=300)
    if len(review) < 10:
        raise ManifestError("schema_compatibility_review must reference a real review")
    return review


def _rollback_schema_not_newer(rollback_head: str, forward_head: str) -> None:
    """The rollback API must target an older or equal schema; never a newer one."""
    if rollback_head.isdigit() and forward_head.isdigit():
        if int(rollback_head) > int(forward_head):
            raise ManifestError("rollback API migration head is newer than the forward schema")


def _load_json(path: Path) -> dict[str, Any]:
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
    return value


def _common_header(value: dict[str, Any]) -> str:
    if value["environment"] != "staging":
        raise ManifestError("only the staging environment is accepted")
    variant = value["deployment_variant"]
    if variant not in {"edge", "standalone"}:
        raise ManifestError("deployment_variant must be edge or standalone")
    return variant


@dataclass(frozen=True)
class Component:
    release_commit: str
    image: str


@dataclass(frozen=True)
class ReleaseManifest:
    deployment_variant: str
    release_commit: str
    migration_head: str
    api_image: str
    web_image: str
    created_at: str
    created_by: str
    rollback_api: Component
    rollback_api_migration_head: str
    rollback_web: Component
    schema_compatibility_review: str

    def compose_env(self, *, rollback: bool = False) -> str:
        if rollback:
            api, web = self.rollback_api, self.rollback_web
            api_head = self.rollback_api_migration_head
        else:
            api = Component(self.release_commit, self.api_image)
            web = Component(self.release_commit, self.web_image)
            api_head = self.migration_head
        return "\n".join(
            (
                "MF_ENV=staging",
                f"MF_DEPLOYMENT_VARIANT={self.deployment_variant}",
                f"MF_RELEASE_COMMIT={self.release_commit}",
                f"MF_MIGRATION_HEAD={self.migration_head}",
                f"MF_API_COMMIT={api.release_commit}",
                f"MF_WEB_COMMIT={web.release_commit}",
                f"MF_API_MIGRATION_HEAD={api_head}",
                f"MF_API_IMAGE={api.image}",
                f"MF_WEB_IMAGE={web.image}",
                "",
            )
        )


LEGACY_V1_KEYS = RELEASE_KEYS
LEGACY_V1_ROLLBACK_KEYS = {"release_commit", "api_image", "web_image", "database_strategy"}


def _any_image(value: Any, field: str) -> str:
    candidate = _required_string(value, field)
    if not IMAGE_RE.fullmatch(candidate):
        raise ManifestError(f"{field} must be an OCI image pinned by sha256 digest")
    host = candidate.split("/", 1)[0].split(":", 1)
    if len(host) == 2 and not 1 <= int(host[1]) <= 65535:
        raise ManifestError(f"{field} contains an invalid registry port")
    return candidate


def load_legacy_receipt(value: dict[str, Any]) -> ReleaseManifest:
    """Read a schema_version 1 receipt already deployed on staging (scheduled jobs only).

    The original v1 rules are applied unchanged. A v1 manifest can never drive a new
    release or rollback: ``validate`` and ``emit-rollback-env`` require version 2.
    """
    _exact_keys(value, LEGACY_V1_KEYS, "manifest")
    variant = _common_header(value)
    release_commit = _commit(value["release_commit"], "release_commit")
    migration_head = _migration(value["migration_head"], "migration_head")
    api_image = _any_image(value["api_image"], "api_image")
    web_image = _any_image(value["web_image"], "web_image")
    rollback = _exact_keys(value["rollback"], LEGACY_V1_ROLLBACK_KEYS, "rollback")
    rollback_commit = _commit(rollback["release_commit"], "rollback.release_commit")
    rollback_api = Component(rollback_commit, _any_image(rollback["api_image"], "rollback.api_image"))
    rollback_web = Component(rollback_commit, _any_image(rollback["web_image"], "rollback.web_image"))
    if _required_string(rollback["database_strategy"], "rollback.database_strategy") != DATABASE_STRATEGY:
        raise ManifestError("rollback must keep the migrated schema forward")
    if rollback_commit == release_commit:
        raise ManifestError("rollback release must differ from the target release")
    if rollback_api.image == api_image and rollback_web.image == web_image:
        raise ManifestError("rollback images must differ from the target images")
    return ReleaseManifest(
        deployment_variant=variant,
        release_commit=release_commit,
        migration_head=migration_head,
        api_image=api_image,
        web_image=web_image,
        created_at=_utc_timestamp(value["created_at"]),
        created_by=_required_string(value["created_by"], "created_by", max_length=120),
        rollback_api=rollback_api,
        rollback_api_migration_head=migration_head,
        rollback_web=rollback_web,
        schema_compatibility_review="legacy v1 receipt",
    )


def load_manifest(path: Path, *, allow_legacy_receipt: bool = False) -> ReleaseManifest:
    value = _load_json(path)
    if allow_legacy_receipt and type(value.get("schema_version")) is int and value["schema_version"] == 1:
        return load_legacy_receipt(value)
    if type(value.get("schema_version")) is not int or value["schema_version"] != 2:
        raise ManifestError(
            "schema_version must be integer 2 (version 1 cannot express distinct "
            "API/web rollback commits and is no longer accepted)"
        )
    _exact_keys(value, RELEASE_KEYS, "manifest")
    variant = _common_header(value)
    release_commit = _commit(value["release_commit"], "release_commit")
    migration_head = _migration(value["migration_head"], "migration_head")
    api_image = _signed_image(value["api_image"], "api_image", "api")
    web_image = _signed_image(value["web_image"], "web_image", "web")

    rollback = _exact_keys(value["rollback"], ROLLBACK_KEYS, "rollback")
    if rollback["database_strategy"] != DATABASE_STRATEGY:
        raise ManifestError("rollback must keep the migrated schema forward")
    api = _exact_keys(rollback["api"], ROLLBACK_API_KEYS, "rollback.api")
    web = _exact_keys(rollback["web"], ROLLBACK_WEB_KEYS, "rollback.web")
    rollback_api = Component(
        _commit(api["release_commit"], "rollback.api.release_commit"),
        _signed_image(api["image"], "rollback.api.image", "api"),
    )
    rollback_web = Component(
        _commit(web["release_commit"], "rollback.web.release_commit"),
        _signed_image(web["image"], "rollback.web.image", "web"),
    )
    rollback_head = _migration(api["migration_head"], "rollback.api.migration_head")
    _rollback_schema_not_newer(rollback_head, migration_head)
    review = _review(rollback["schema_compatibility_review"])
    # A rollback is complete only if both components point to a previous build.
    for name, component, target in (
        ("api", rollback_api, api_image),
        ("web", rollback_web, web_image),
    ):
        if component.release_commit == release_commit:
            raise ManifestError(f"rollback.{name} release must differ from the target release")
        if component.image == target:
            raise ManifestError(f"rollback.{name} image must differ from the target image")

    return ReleaseManifest(
        deployment_variant=variant,
        release_commit=release_commit,
        migration_head=migration_head,
        api_image=api_image,
        web_image=web_image,
        created_at=_utc_timestamp(value["created_at"]),
        created_by=_required_string(value["created_by"], "created_by", max_length=120),
        rollback_api=rollback_api,
        rollback_api_migration_head=rollback_head,
        rollback_web=rollback_web,
        schema_compatibility_review=review,
    )


@dataclass(frozen=True)
class LocalImage:
    component: str
    release_commit: str
    image_id: str
    archive: str
    archive_sha256: str

    @property
    def local_tag(self) -> str:
        # Never a registry host: the reference cannot be mistaken for a GHCR artifact.
        return f"{LOCAL_FALLBACK_NAMESPACE}/{self.component}:{self.release_commit}"


@dataclass(frozen=True)
class FallbackManifest:
    deployment_variant: str
    forward_migration_head: str
    api_migration_head: str
    api: LocalImage
    web: LocalImage
    schema_compatibility_review: str
    created_at: str
    created_by: str

    def compose_env(self) -> str:
        return "\n".join(
            (
                "MF_ENV=staging",
                f"MF_DEPLOYMENT_VARIANT={self.deployment_variant}",
                f"MF_MIGRATION_HEAD={self.forward_migration_head}",
                f"MF_API_COMMIT={self.api.release_commit}",
                f"MF_WEB_COMMIT={self.web.release_commit}",
                f"MF_API_MIGRATION_HEAD={self.api_migration_head}",
                f"MF_API_IMAGE={self.api.local_tag}",
                f"MF_WEB_IMAGE={self.web.local_tag}",
                f"MF_API_IMAGE_ID={self.api.image_id}",
                f"MF_WEB_IMAGE_ID={self.web.image_id}",
                f"MF_API_ARCHIVE={self.api.archive}",
                f"MF_WEB_ARCHIVE={self.web.archive}",
                f"MF_API_ARCHIVE_SHA256={self.api.archive_sha256}",
                f"MF_WEB_ARCHIVE_SHA256={self.web.archive_sha256}",
                "",
            )
        )


def _archive_path(value: Any, field: str) -> str:
    candidate = _required_string(value, field, max_length=255)
    path = PurePosixPath(candidate)
    if not path.is_absolute() or ".." in path.parts or not candidate.endswith(".tar"):
        raise ManifestError(f"{field} must be an absolute .tar path without '..'")
    if not re.fullmatch(r"[A-Za-z0-9_./+-]+", candidate):
        raise ManifestError(f"{field} contains unsupported characters")
    return candidate


def _local_image(value: Any, component: str, keys: set[str]) -> LocalImage:
    item = _exact_keys(value, keys, component)
    image_id = _required_string(item["image_id"], f"{component}.image_id", max_length=71)
    if not IMAGE_ID_RE.fullmatch(image_id):
        raise ManifestError(f"{component}.image_id must be sha256:<64 hex>")
    archive_sha = _required_string(
        item["archive_sha256"], f"{component}.archive_sha256", max_length=64
    )
    if not DIGEST_HEX_RE.fullmatch(archive_sha):
        raise ManifestError(f"{component}.archive_sha256 must be 64 lowercase hex characters")
    return LocalImage(
        component=component,
        release_commit=_commit(item["release_commit"], f"{component}.release_commit"),
        image_id=image_id,
        archive=_archive_path(item["archive"], f"{component}.archive"),
        archive_sha256=archive_sha,
    )


def load_fallback_manifest(path: Path) -> FallbackManifest:
    value = _load_json(path)
    _exact_keys(value, FALLBACK_KEYS, "fallback manifest")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ManifestError("fallback schema_version must be integer 1")
    if value["kind"] != "local-fallback-rollback":
        raise ManifestError("kind must be local-fallback-rollback")
    if value["provenance"] != "local-archive-unsigned":
        raise ManifestError("provenance must be declared as local-archive-unsigned")
    variant = _common_header(value)
    if value["database_strategy"] != DATABASE_STRATEGY:
        raise ManifestError("fallback rollback must keep the migrated schema forward")
    forward_head = _migration(value["forward_migration_head"], "forward_migration_head")
    api_value = _exact_keys(value["api"], FALLBACK_API_KEYS, "api")
    api_head = _migration(api_value["migration_head"], "api.migration_head")
    _rollback_schema_not_newer(api_head, forward_head)
    api = _local_image(api_value, "api", FALLBACK_API_KEYS)
    web = _local_image(value["web"], "web", FALLBACK_WEB_KEYS)
    if api.archive == web.archive or api.image_id == web.image_id:
        raise ManifestError("api and web must reference distinct archives and images")
    return FallbackManifest(
        deployment_variant=variant,
        forward_migration_head=forward_head,
        api_migration_head=api_head,
        api=api,
        web=web,
        schema_compatibility_review=_review(value["schema_compatibility_review"]),
        created_at=_utc_timestamp(value["created_at"]),
        created_by=_required_string(value["created_by"], "created_by", max_length=120),
    )


def _registry_qualified(reference: str) -> bool:
    first = reference.split("/", 1)[0]
    return "/" in reference and ("." in first or ":" in first or first == "localhost")


def inspect_archive(path: Path, expected_sha256: str, image_id: str) -> list[str]:
    """Check a ``docker save`` archive before any ``docker load``; return its RepoTags.

    The archive hash must match the manifest, the archive must hold exactly one image and
    that image must be the declared ``image_id`` (config digest for the classic store,
    manifest digest listed in index.json for the containerd store).
    """
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ManifestError("archive is not readable") from error
    if digest.hexdigest() != expected_sha256:
        raise ManifestError("archive SHA256 does not match the fallback manifest")
    wanted = image_id.split(":", 1)[1]
    try:
        with tarfile.open(path, mode="r:") as archive:
            members = {member.name.lstrip("./"): member for member in archive.getmembers()}

            def read_json(name: str) -> Any:
                member = members.get(name)
                if member is None:
                    return None
                if not member.isfile() or member.size > MAX_ARCHIVE_INDEX_BYTES:
                    raise ManifestError(f"archive {name} is not a bounded regular file")
                handle = archive.extractfile(member)
                assert handle is not None
                return json.loads(handle.read(), object_pairs_hook=_strict_object)

            manifest = read_json("manifest.json")
            index = read_json("index.json")
    except (tarfile.TarError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManifestError("archive is not a readable docker save tarball") from error
    if not isinstance(manifest, list) or len(manifest) != 1 or not isinstance(manifest[0], dict):
        raise ManifestError("archive must contain exactly one image")
    candidates: set[str] = set()
    config = manifest[0].get("Config")
    if isinstance(config, str):
        candidates.add(PurePosixPath(config).name.removesuffix(".json"))
    if isinstance(index, dict):
        for entry in index.get("manifests") or []:
            if isinstance(entry, dict) and isinstance(entry.get("digest"), str):
                candidates.add(entry["digest"].removeprefix("sha256:"))
    if wanted not in candidates:
        raise ManifestError("archive does not contain the declared image_id")
    tags = manifest[0].get("RepoTags") or []
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ManifestError("archive RepoTags are malformed")
    return tags


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "validate",
            "emit-release-env",
            "emit-rollback-env",
            "validate-fallback",
            "emit-fallback-env",
            "check-archive",
        ),
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("component", nargs="?", choices=("api", "web"))
    args = parser.parse_args(argv)
    try:
        if args.command in {"validate-fallback", "emit-fallback-env", "check-archive"}:
            fallback = load_fallback_manifest(args.manifest)
            if args.command == "validate-fallback":
                print(
                    "OK: local fallback rollback manifest (UNSIGNED local archives) "
                    f"api={fallback.api.release_commit[:12]} "
                    f"web={fallback.web.release_commit[:12]} "
                    f"forward-schema={fallback.forward_migration_head}"
                )
            elif args.command == "emit-fallback-env":
                sys.stdout.write(fallback.compose_env())
            else:
                if args.component is None:
                    raise ManifestError("check-archive requires api or web")
                image = fallback.api if args.component == "api" else fallback.web
                tags = inspect_archive(Path(image.archive), image.archive_sha256, image.image_id)
                registry_tags = [tag for tag in tags if _registry_qualified(tag)]
                print("REGISTRY_TAGS=" + ("yes" if registry_tags else "no"))
            return 0
        # Only the deployed-receipt reader (run-scheduled-job.sh) still accepts v1.
        manifest = load_manifest(
            args.manifest, allow_legacy_receipt=args.command == "emit-release-env"
        )
    except ManifestError as error:
        print(f"FAIL: invalid staging release manifest: {error}", file=sys.stderr)
        return 2
    if args.command == "validate":
        print(
            "OK: signed staging release manifest "
            f"{manifest.release_commit[:12]} migration={manifest.migration_head} "
            f"rollback api={manifest.rollback_api.release_commit[:12]} "
            f"web={manifest.rollback_web.release_commit[:12]} "
            f"variant={manifest.deployment_variant}"
        )
    elif args.command == "emit-release-env":
        sys.stdout.write(manifest.compose_env())
    else:
        sys.stdout.write(manifest.compose_env(rollback=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
