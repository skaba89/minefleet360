#!/bin/bash
# Sauvegarde quotidienne de la base de démo (cron). Rétention locale : 7 fichiers.
# Copie hors machine (OVH Object Storage) : à décider (C-09, coût).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p backups
docker compose -f docker-compose.demo.yml --env-file .env.demo exec -T db \
  pg_dump -U postgres -Fc minefleet > "backups/minefleet-$(date -u +%Y%m%dT%H%M%SZ).dump"
ls -1t backups/*.dump | tail -n +8 | xargs -r rm --
