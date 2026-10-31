#!/bin/bash
# Sauvegarde quotidienne de la base (cron). Rétention locale : 7 fichiers.
# Copie hors machine (D-41, C-09) : chiffrée AES-256 (gpg) puis envoyée par rclone vers la destination
# choisie (OVH Object Storage, autre S3, SFTP…), UNIQUEMENT si offsite.env existe (voir offsite.env.example).
set -euo pipefail
umask 077  # dumps lisibles par le seul propriétaire (données, même fictives)
cd "$(dirname "$0")"
mkdir -p backups
chmod 700 backups
dump="backups/minefleet-$(date -u +%Y%m%dT%H%M%SZ).dump"
# Write to a temporary file: a failed dump must never look like a usable backup.
partial="$dump.partial"
trap 'rm -f -- "$partial"' EXIT
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T db \\
  pg_dump -U postgres -Fc minefleet > "$partial" </dev/null
if [ ! -s "$partial" ]; then
  echo "FAIL: PostgreSQL dump is empty" >&2
  exit 1
fi
# pg_restore --list checks archive readability without restoring production data.
if ! docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T db \\
  pg_restore --list < "$partial" > /dev/null; then
  echo "FAIL: PostgreSQL backup archive is invalid" >&2
  exit 1
fi
mv -- "$partial" "$dump"
trap - EXIT
# Keep recent local recovery points even if later offsite encryption/upload fails.

if [ ! -f offsite.env ]; then
  echo "WARNING: backup only local; offsite backup NOT configured (offsite.env absent)" >&2
  ls -1t backups/*.dump | tail -n +8 | xargs -r rm --
  exit 0
fi
# shellcheck source=/dev/null
. ./offsite.env
: "${MF_OFFSITE_REMOTE:?MF_OFFSITE_REMOTE manquant dans offsite.env}"
: "${MF_OFFSITE_PASSPHRASE_FILE:?MF_OFFSITE_PASSPHRASE_FILE manquant dans offsite.env}"
retention="${MF_OFFSITE_RETENTION_DAYS:-30}"
if [ ! -r "$MF_OFFSITE_PASSPHRASE_FILE" ]; then
  echo "phrase de chiffrement illisible : $MF_OFFSITE_PASSPHRASE_FILE" >&2
  exit 1
fi
# Jamais de dump en clair hors du serveur : chiffrement symétrique authentifié (MDC) avant tout envoi.
encrypted="$dump.gpg"
gpg --batch --yes --quiet --pinentry-mode loopback --symmetric --cipher-algo AES256 \
  --passphrase-file "$MF_OFFSITE_PASSPHRASE_FILE" --output "$encrypted" "$dump"
rclone copy --quiet "$encrypted" "$MF_OFFSITE_REMOTE" </dev/null
rm -f -- "$encrypted"
# Apply local retention only once the current archive has been verified and transferred.
ls -1t backups/*.dump | tail -n +8 | xargs -r rm --
# Rétention distante (jours) : les copies plus anciennes sont supprimées de la destination.
rclone delete --quiet --min-age "${retention}d" "$MF_OFFSITE_REMOTE" </dev/null
echo "copie hors machine : $(basename "$encrypted") envoyée vers $MF_OFFSITE_REMOTE (rétention ${retention} j)"
