#!/bin/bash
# Sauvegarde quotidienne de la base (cron). Rétention locale : 7 fichiers.
# Copie hors machine (OVH Object Storage) : à décider (C-09, coût) ; chiffrer avant tout transfert.
set -euo pipefail
umask 077  # dumps lisibles par le seul propriétaire (données, même fictives)
cd "$(dirname "$0")"
mkdir -p backups
chmod 700 backups
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T db \
  pg_dump -U postgres -Fc minefleet > "backups/minefleet-$(date -u +%Y%m%dT%H%M%SZ).dump"
ls -1t backups/*.dump | tail -n +8 | xargs -r rm --
