#!/bin/bash
# Sauvegarde quotidienne de la base (cron). Rétention locale : 7 fichiers.
# Copie hors machine (D-41, C-09) : déléguée au transport strict, chiffré et borné
# upload-offsite-backup.sh si offsite.env existe (voir offsite.env.example).
set -euo pipefail
umask 077  # dumps lisibles par le seul propriétaire (données, même fictives)
script_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$script_dir"
backup_dir="${MF_BACKUP_DIR:-backups}"
if [[ "$backup_dir" != /* ]]; then
  backup_dir="$(pwd)/$backup_dir"
fi
if [[ -L "$backup_dir" ]]; then
  echo "FAIL: backup directory must not be a symlink" >&2
  exit 1
fi
mkdir -p -- "$backup_dir"
chmod 700 "$backup_dir"
dump="$backup_dir/minefleet-$(date -u +%Y%m%dT%H%M%SZ).dump"
# Write to a temporary file: a failed dump must never look like a usable backup.
partial="$dump.partial"
trap 'rm -f -- "$partial"' EXIT
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T db \
  pg_dump -U postgres -Fc minefleet > "$partial" </dev/null
if [ ! -s "$partial" ]; then
  echo "FAIL: PostgreSQL dump is empty" >&2
  exit 1
fi
# pg_restore --list checks archive readability without restoring production data.
if ! docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T db \
  pg_restore --list < "$partial" > /dev/null; then
  echo "FAIL: PostgreSQL backup archive is invalid" >&2
  exit 1
fi
mv -- "$partial" "$dump"
trap - EXIT
# Keep recent local recovery points even if later offsite encryption/upload fails.

offsite_config_file="${MF_OFFSITE_CONFIG_FILE:-$script_dir/offsite.env}"
if [[ ! -e "$offsite_config_file" && ! -L "$offsite_config_file" ]]; then
  echo "WARNING: backup only local; offsite backup NOT configured (offsite.env absent)" >&2
  find "$backup_dir" -maxdepth 1 -type f -name 'minefleet-*.dump' -printf '%T@ %p\0' \
    | sort -zrn | tail -z -n +8 | cut -z -d' ' -f2- | xargs -0r rm --
  exit 0
fi
MF_OFFSITE_CONFIG_FILE="$offsite_config_file" bash "$script_dir/upload-offsite-backup.sh" "$dump"
# Apply local retention only once the current archive has been verified and transferred.
find "$backup_dir" -maxdepth 1 -type f -name 'minefleet-*.dump' -printf '%T@ %p\0' \
  | sort -zrn | tail -z -n +8 | cut -z -d' ' -f2- | xargs -0r rm --
