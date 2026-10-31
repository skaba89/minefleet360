#!/usr/bin/env python3
"""Aggregate repeated operational probe failures into alert/recovery events.

Designed for cron. No outbound traffic and no secrets in output. An external
monitor can act on ALERT/RECOVERED exit-0 lines, or inspect state safely.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

def transition(previous: dict[str, object], result: int, threshold: int) -> tuple[dict[str, object], str]:
    failures = int(previous.get("failures", 0))
    active = bool(previous.get("active", False))
    if result == 0:
        return {"failures": 0, "active": False}, "RECOVERED" if active else "OK"
    if result not in (2, 3):
        result = 3
    failures = min(failures + 1, threshold)
    if failures >= threshold and not active:
        return {"failures": failures, "active": True}, "ALERT"
    return {"failures": failures, "active": active}, "ALERT_ACTIVE" if active else "PENDING"

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--threshold", type=int, default=3)
    parser.add_argument("--probe", type=Path, default=Path(__file__).with_name("probe-all.sh"))
    args = parser.parse_args()
    if not 1 <= args.threshold <= 100:
        parser.error("threshold must be between 1 and 100")
    args.state_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(args.state_file, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "r+", encoding="utf-8") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                old = json.load(stream)
                if not isinstance(old, dict):
                    raise ValueError("invalid state")
            except (ValueError, json.JSONDecodeError):
                old = {}
            try:
                run = subprocess.run(["bash", str(args.probe.resolve())], capture_output=True, timeout=75, check=False)
                result = run.returncode
            except (OSError, subprocess.TimeoutExpired):
                result = 3
            new, event = transition(old, result, args.threshold)
            stream.seek(0)
            json.dump(new, stream)
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
            print(f"{event}: operational probe exit={result}")
    finally:
        pass
    return 0

if __name__ == "__main__":
    sys.exit(main())
