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
    queue_file = args.state_dir / "pending-notifications.json"
    lock_file = args.state_dir / "monitor.lock"

    with os.fdopen(os.open(lock_file, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if queue_file.is_symlink():
            print("ERROR: queue file must not be a symlink", file=sys.stderr)
            return 3
        try:
            raw = json.loads(queue_file.read_text()) if queue_file.exists() else []
            if not isinstance(raw, list) or any(x not in EVENTS for x in raw):
                raise ValueError("invalid queue")
            queue = raw
        except (OSError, ValueError):
            print("ERROR: notification queue cannot be read", file=sys.stderr)
            return 3

        def persist() -> None:
            temp = args.state_dir / f".pending-{os.getpid()}.tmp"
            try:
                with os.fdopen(os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600), "w") as out:
                    json.dump(queue, out)
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(temp, queue_file)
            finally:
                temp.unlink(missing_ok=True)

        # Never start delivery before the event has been durably queued.
        try:
            probe = subprocess.run(
                [sys.executable, str(scripts / "alert-state.py"),
                 "--state-file", str(args.state_dir / "health-state.json"),
                 "--threshold", str(args.threshold)],
                capture_output=True, text=True, timeout=95, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            print("ERROR: operational alert check failed", file=sys.stderr)
            return 3
        if probe.returncode != 0:
            print("ERROR: operational alert check returned failure", file=sys.stderr)
            return 3
        updated = add_event(queue, probe.stdout.strip())
        if updated != queue:
            queue = updated
            persist()
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
            event = queue.pop(0)
            persist()
            print(f"DELIVERED: {event} notification accepted by SMTP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
