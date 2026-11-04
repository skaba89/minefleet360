#!/usr/bin/env bash
# Read-only check of MineFleet scheduled jobs (systemd oneshot services run by timers).
# Exit 0 OK, 2 CRITICAL (failed, unsuccessful or stale run), 3 UNKNOWN (not installed, never run, bad config).
# Without this probe a failing nightly job (HSE digest, preventive dues) would go unnoticed.
set -uo pipefail
units="${MF_SCHEDULED_UNITS:-minefleet-hse-digest minefleet-preventive-evaluate}"
max_age="${MF_SCHEDULED_MAX_AGE_HOURS:-26}"
if [[ ! "$max_age" =~ ^[1-9][0-9]*$ ]] || (( max_age > 720 )); then
  echo "UNKNOWN: MF_SCHEDULED_MAX_AGE_HOURS must be an integer 1..720" >&2
  exit 3
fi
command -v systemctl >/dev/null || { echo "UNKNOWN: systemctl missing" >&2; exit 3; }
now="$(date +%s)"
critical=0
unknown=0
for unit in $units; do
  if [[ ! "$unit" =~ ^[a-z0-9-]+$ ]]; then
    echo "UNKNOWN: invalid unit name" >&2
    exit 3
  fi
  if [[ "$(systemctl show "$unit.service" -p LoadState --value 2>/dev/null)" != "loaded" ]]; then
    echo "UNKNOWN: $unit not installed" >&2
    unknown=1
    continue
  fi
  if systemctl is-failed --quiet "$unit.service"; then
    echo "CRITICAL: $unit failed" >&2
    critical=1
    continue
  fi
  result="$(systemctl show "$unit.service" -p Result --value 2>/dev/null)"
  last="$(systemctl show "$unit.service" -p ExecMainExitTimestamp --value 2>/dev/null)"
  if [[ -z "$last" || "$last" == "n/a" ]]; then
    echo "UNKNOWN: $unit has never run" >&2
    unknown=1
    continue
  fi
  if ! last_epoch="$(date -d "$last" +%s 2>/dev/null)"; then
    echo "UNKNOWN: cannot parse $unit timestamp" >&2
    unknown=1
    continue
  fi
  if [[ "$result" != "success" ]]; then
    echo "CRITICAL: $unit last run unsuccessful" >&2
    critical=1
  elif (( now - last_epoch > max_age * 3600 )); then
    echo "CRITICAL: $unit has not run for more than ${max_age}h" >&2
    critical=1
  fi
done
(( critical )) && exit 2
(( unknown )) && exit 3
echo "OK: scheduled jobs ran successfully within ${max_age}h"
exit 0
