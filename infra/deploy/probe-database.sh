#!/usr/bin/env bash
# Contrôle de disponibilité PostgreSQL en lecture seule, depuis l'hôte Docker MineFleet.
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -f .env.prod ]]; then
  echo "UNKNOWN: configuration .env.prod absente" >&2
  exit 3
fi
if ! command -v docker >/dev/null 2>&1 || ! command -v timeout >/dev/null 2>&1; then
  echo "UNKNOWN: docker et timeout requis" >&2
  exit 3
fi
# Execute within the private DB container. No database ports are published or passwords logged.
if ! timeout 15 docker compose -f docker-compose.prod.yml --env-file .env.prod \
  exec -T db pg_isready -q -U postgres -d minefleet >/dev/null 2>&1; then
  echo "CRITICAL: PostgreSQL not accepting connections" >&2
  exit 2
fi
# pg_isready alone can succeed without the target database being queryable.
if ! timeout 15 docker compose -f docker-compose.prod.yml --env-file .env.prod \
  exec -T -u postgres db psql -X -q -t -A -v ON_ERROR_STOP=1 \
  -U postgres -d minefleet -c 'SELECT 1' 2>/dev/null | grep -qx 1; then
  echo "CRITICAL: PostgreSQL read-only query failed" >&2
  exit 2
fi
echo "OK: PostgreSQL accepts connections and SELECT 1 succeeded"
