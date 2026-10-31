"""Crash-resistant persistence for the operational monitor state."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def read_state(path: Path) -> dict:
    if not path.exists():
        return {}
    if path.is_symlink():
        raise ValueError("symlink state refused")
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("invalid state format")
    return value


def write_state(path: Path, value: dict) -> None:
    if path.is_symlink():
        raise ValueError("symlink state refused")
    data = json.dumps(value, separators=(",", ":")).encode()
    tmp_name = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=".health-", suffix=".tmp", dir=path.parent)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
        tmp_name = None
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if tmp_name:
            os.unlink(tmp_name)
