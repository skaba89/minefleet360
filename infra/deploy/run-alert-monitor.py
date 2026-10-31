#!/usr/bin/env python3
"""Run operational checks, persist alert transitions, retry SMTP deliveries.

At-least-once delivery: SMTP may accept a message immediately before an
unexpected crash; a subsequent retry can duplicate it. No message is discarded
on a reported SMTP failure.
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

EVENTS = {"ALERT", "RECOVERED"}


def add_event(queue: list[str], line: str) -> list[str]:
    event = line.partition(":")[0].strip()
    return [*queue, event] if event in EVENTS else queue


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--threshold", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.threshold <= 100:
        parser.error("threshold must be 1..100")
    args.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.state_dir.is_symlink():
        print("ERROR: state directory must not be a symlink", file=sys.stderr)
        return 3
    scripts = Path(__file__).resolve().parent
    state_file = args.state_dir / "health-state.json"
    lock_file = args.state_dir / "monitor.lock"

    with os.fdopen(os.open(lock_file, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            probe = subprocess.run(
                [sys.executable, str(scripts / "alert-state.py"),
                 "--state-file", str(state_file), "--threshold", str(args.threshold)],
                capture_output=True, text=True, timeout=95, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            print("ERROR: operational alert check failed", file=sys.stderr)
            return 3
        if probe.returncode != 0:
            print("ERROR: operational alert check returned failure", file=sys.stderr)
            return 3

        # Lock a stable inode: replacing health-state.json itself invalidates file locks.
        state_lock = state_file.with_name(state_file.name + ".lock")
        with os.fdopen(os.open(state_lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600), "r+") as state_guard:
            fcntl.flock(state_guard, fcntl.LOCK_EX)
            try:
                state = read_state(state_file)
                queue = state["pending_notifications"]
                if not isinstance(queue, list) or any(x not in EVENTS for x in queue):
                    raise ValueError("invalid outbox")
            except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError):
                print("ERROR: invalid monitoring state", file=sys.stderr)
                return 3
            while queue:
                try:
                    result = subprocess.run(
                        [sys.executable, str(scripts / "notify-alert-smtp.py"), queue[0]],
                        capture_output=True, timeout=30, check=False,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    print("WARNING: SMTP delivery failed; event retained", file=sys.stderr)
                    return 2
                if result.returncode != 0:
                    print("WARNING: SMTP delivery failed; event retained", file=sys.stderr)
                    return 2
                event = queue[0]
                state["pending_notifications"] = queue[1:]
                write_state(state_file, state)
                queue = state["pending_notifications"]
                print(f"DELIVERED: {event} notification accepted by SMTP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
