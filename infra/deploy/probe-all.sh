#!/usr/bin/env bash
# Aggregates MineFleet checks without secrets or raw operational data in output.
# Exit 0 = all checks OK, 2 = one or more critical, 3 = configuration/error.
set -uo pipefail
cd "$(dirname "$0")"
failed=0
unknown=0

run_check() {
  local label="$1" script="$2" output code
  output="$(bash "$script" 2>&1)"
  code=$?
  case "$code" in
    0) echo "OK: $label" ;;
    2) echo "CRITICAL: $label"; failed=1 ;;
    *) echo "UNKNOWN: $label"; unknown=1 ;;
  esac
  # Never echo output: configuration, URLs and diagnostic details may be sensitive.
}

run_check "PostgreSQL" "./probe-database.sh"
run_check "Local backup freshness" "./probe-backup-freshness.sh"
if [[ -n "${MINEFLEET_BASE_URL:-}" ]]; then
  run_check "External HTTPS API" "./probe-health.sh"
else
  echo "UNKNOWN: External HTTPS API not configured (MINEFLEET_BASE_URL)"
  unknown=1
fi
if (( failed )); then
  echo "CRITICAL: MineFleet operational checks failed"
  exit 2
fi
if (( unknown )); then
  echo "UNKNOWN: MineFleet operational checks incomplete"
  exit 3
fi
echo "OK: all configured MineFleet operational checks passed"
