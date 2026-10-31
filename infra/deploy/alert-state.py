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

from monitor_state import read_state, write_state

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
    lock_path = args.state_file.with_name(args.state_file.name + ".lock")
    with os.fdopen(os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600), "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            old = read_state(args.state_file)
        except (ValueError, OSError, json.JSONDecodeError):
            print("ERROR: monitoring state unreadable; refusing to overwrite", file=sys.stderr)
            return 3
        try:
            run = subprocess.run(["bash", str(args.probe.resolve())], capture_output=True, timeout=75, check=False)
            result = run.returncode
        except (OSError, subprocess.TimeoutExpired):
            result = 3
        new, event = transition(old, result, args.threshold)
        pending = old.get("pending_notifications", [])
        if not isinstance(pending, list) or any(x not in ("ALERT", "RECOVERED") for x in pending):
            print("ERROR: invalid notification outbox", file=sys.stderr)
            return 3
        if event in ("ALERT", "RECOVERED"):
            pending = [*pending, event]
        new["pending_notifications"] = pending
        write_state(args.state_file, new)
        print(f"{event}: operational probe exit={result}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
