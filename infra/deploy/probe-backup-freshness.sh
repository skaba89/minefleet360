#!/usr/bin/env bash
# Read-only local backup freshness check. Exit 0 OK, 2 CRITICAL, 3 UNKNOWN.
set -euo pipefail
cd "$(dirname "$0")"
directory="${MF_BACKUP_DIR:-backups}"
max_age="${MF_BACKUP_MAX_AGE_HOURS:-26}"
if [[ ! "$max_age" =~ ^[1-9][0-9]*$ ]] || (( max_age > 720 )); then
  echo "UNKNOWN: MF_BACKUP_MAX_AGE_HOURS must be an integer 1..720" >&2
  exit 3
fi
if [[ ! -d "$directory" ]]; then
  echo "CRITICAL: backup directory missing" >&2
  exit 2
fi
newest=""
newest_time=0
shopt -s nullglob
for file in "$directory"/minefleet-*.dump; do
  [[ -f "$file" && -s "$file" ]] || continue
  if ! timestamp="$(stat -c %Y -- "$file" 2>/dev/null)"; then
    echo "UNKNOWN: cannot inspect backup timestamp" >&2
    exit 3
  fi
  if (( timestamp > newest_time )); then
    newest_time="$timestamp"
    newest="$file"
  fi
done
if [[ -z "$newest" ]]; then
  echo "CRITICAL: no nonempty PostgreSQL backup found" >&2
  exit 2
fi
now="$(date +%s)"
age_seconds="$(( now - newest_time ))"
if (( age_seconds < 0 )); then
  echo "UNKNOWN: backup timestamp is in the future; check clock synchronization" >&2
  exit 3
fi
age_hours="$(( age_seconds / 3600 ))"
if (( age_seconds > max_age * 3600 )); then
  echo "CRITICAL: newest backup older than threshold (${age_hours}h > ${max_age}h)" >&2
  exit 2
fi
echo "OK: latest local backup is ${age_hours}h old (threshold ${max_age}h)"
echo "NOTICE: local freshness does not prove archive integrity, offsite transfer or successful restore"
