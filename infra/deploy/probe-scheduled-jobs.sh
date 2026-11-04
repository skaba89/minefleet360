#!/usr/bin/env bash
# Read-only check of MineFleet scheduled jobs (systemd oneshot services run by timers).
# Exit 0 OK, 2 CRITICAL (failed, unsuccessful or stale run), 3 UNKNOWN (not installed, never run, bad config).
# Without this probe a failing nightly job (HSE digest, preventive dues) would go unnoticed.
set -uo pipefail
# Entrées « unité » ou « unité:heures » (délai maximal propre à la tâche, sinon MF_SCHEDULED_MAX_AGE_HOURS).
units="${MF_SCHEDULED_UNITS:-minefleet-hse-digest minefleet-preventive-evaluate minefleet-gps-signal-sweep:1 minefleet-notify-deliver:1}"
max_age="${MF_SCHEDULED_MAX_AGE_HOURS:-26}"
if [[ ! "$max_age" =~ ^[1-9][0-9]*$ ]] || (( max_age > 720 )); then
  echo "UNKNOWN: MF_SCHEDULED_MAX_AGE_HOURS must be an integer 1..720" >&2
  exit 3
fi
command -v systemctl >/dev/null || { echo "UNKNOWN: systemctl missing" >&2; exit 3; }
now="$(date +%s)"
critical=0
unknown=0
for entry in $units; do
  if [[ ! "$entry" =~ ^[a-z0-9-]+(:[1-9][0-9]*)?$ ]]; then
    echo "UNKNOWN: invalid unit entry" >&2
    exit 3
  fi
  unit="${entry%%:*}"
  unit_max="$max_age"
  [[ "$entry" == *:* ]] && unit_max="${entry##*:}"
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
  elif (( now - last_epoch > unit_max * 3600 )); then
    echo "CRITICAL: $unit has not run for more than ${unit_max}h" >&2
    critical=1
  fi
done
(( critical )) && exit 2
(( unknown )) && exit 3
echo "OK: scheduled jobs ran successfully within ${max_age}h"
exit 0
