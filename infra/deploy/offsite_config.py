#!/usr/bin/env python3
"""Strict, non-executable configuration parser for off-site backups."""

from __future__ import annotations

import re
import sys
from pathlib import Path, PurePosixPath

MAX_CONFIG_BYTES = 4096
REQUIRED_KEYS = {"MF_OFFSITE_REMOTE", "MF_OFFSITE_PASSPHRASE_FILE"}
OPTIONAL_KEYS = {"MF_OFFSITE_RETENTION_DAYS"}
ALLOWED_KEYS = REQUIRED_KEYS | OPTIONAL_KEYS
KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
REMOTE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}:[^\s\x00-\x1f\x7f]+$")


class ConfigError(ValueError):
    """Raised when the off-site configuration is unsafe or malformed."""


def _read_config(path: Path) -> dict[str, str]:
    raw = path.read_bytes()
    if len(raw) > MAX_CONFIG_BYTES:
        raise ConfigError(f"configuration exceeds {MAX_CONFIG_BYTES} bytes")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ConfigError("configuration must be valid UTF-8") from error

    values: dict[str, str] = {}
    for number, original in enumerate(text.splitlines(), start=1):
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"line {number} must be KEY=value")
        key, value = line.split("=", 1)
        if not KEY_RE.fullmatch(key):
            raise ConfigError(f"line {number} has an invalid key")
        if key not in ALLOWED_KEYS:
            raise ConfigError(f"unknown key: {key}")
        if key in values:
            raise ConfigError(f"duplicate key: {key}")
        if not value or value != value.strip():
            raise ConfigError(f"{key} must be a non-empty unquoted value")
        if any(character in value for character in ("\n", "\r", "\x00")):
            raise ConfigError(f"{key} contains a control character")
        values[key] = value

    missing = REQUIRED_KEYS - values.keys()
    if missing:
        raise ConfigError(f"missing key: {min(missing)}")
    return values


def _validate(values: dict[str, str]) -> dict[str, str]:
    remote = values["MF_OFFSITE_REMOTE"]
    if not REMOTE_RE.fullmatch(remote):
        raise ConfigError("MF_OFFSITE_REMOTE must use a named rclone remote")
    remote_path = remote.split(":", 1)[1]
    if any(part == ".." for part in PurePosixPath(remote_path).parts):
        raise ConfigError("MF_OFFSITE_REMOTE must not contain parent traversal")

    passphrase = Path(values["MF_OFFSITE_PASSPHRASE_FILE"])
    if not passphrase.is_absolute() or ".." in passphrase.parts:
        raise ConfigError("MF_OFFSITE_PASSPHRASE_FILE must be an absolute safe path")

    retention_text = values.get("MF_OFFSITE_RETENTION_DAYS", "30")
    if not retention_text.isascii() or not retention_text.isdecimal():
        raise ConfigError("MF_OFFSITE_RETENTION_DAYS must be an integer")
    retention = int(retention_text)
    if not 1 <= retention <= 3650:
        raise ConfigError("MF_OFFSITE_RETENTION_DAYS must be between 1 and 3650")

    return {
        "MF_OFFSITE_REMOTE": remote.rstrip("/"),
        "MF_OFFSITE_PASSPHRASE_FILE": str(passphrase),
        "MF_OFFSITE_RETENTION_DAYS": str(retention),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in {"validate", "emit-env"}:
        print(
            f"Usage: {argv[0]} validate|emit-env /absolute/path/offsite.env",
            file=sys.stderr,
        )
        return 2
    path = Path(argv[2])
    try:
        values = _validate(_read_config(path))
    except (ConfigError, OSError) as error:
        print(f"FAIL: invalid off-site backup configuration: {error}", file=sys.stderr)
        return 2

    if argv[1] == "emit-env":
        for key in (
            "MF_OFFSITE_REMOTE",
            "MF_OFFSITE_PASSPHRASE_FILE",
            "MF_OFFSITE_RETENTION_DAYS",
        ):
            print(f"{key}={values[key]}")
    else:
        print("OK: strict off-site backup configuration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
