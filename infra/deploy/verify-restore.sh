#!/usr/bin/env bash
# Restore a MineFleet pg_dump archive into a disposable, network-isolated PostGIS instance.
# NEVER connects to or modifies the running production database.
set -euo pipefail
umask 077

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /absolute/path/to/minefleet-YYYYMMDD.dump" >&2
  exit 2
fi
archive="$(realpath -- "$1")"
if [[ ! -f "$archive" || ! -s "$archive" ]]; then
  echo "FAIL: archive missing or empty" >&2
  exit 1
fi
command -v docker >/dev/null || { echo "FAIL: docker required" >&2; exit 1; }
name="minefleet-restore-check-$$-$RANDOM"
cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "Starting disposable PostGIS (network disabled, no persistent volumes)..."
docker run -d --rm --name "$name" --network none \
  --mount "type=bind,source=$archive,target=/tmp/backup.dump,readonly" \
  -e POSTGRES_PASSWORD=throwaway-restore-only \
  postgis/postgis:16-3.4 >/dev/null

ready=0
for _ in $(seq 1 40); do
  if docker exec "$name" pg_isready -U postgres >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" != "1" ]]; then
  echo "FAIL: isolated database did not start" >&2
  exit 1
fi

docker exec -u postgres "$name" createdb -U postgres minefleet_restore_check
# A successful catalog listing alone does not prove data can be restored.
docker exec -u postgres "$name" pg_restore \
  --exit-on-error --no-owner --no-acl -U postgres \
  -d minefleet_restore_check /tmp/backup.dump >/dev/null

# Validate real restored relations without logging personal or operational rows.
table_count="$(docker exec -u postgres "$name" psql -U postgres -d minefleet_restore_check -Atc \
  "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='public' AND tablename NOT LIKE 'pg_%';")"
if [[ ! "$table_count" =~ ^[0-9]+$ || "$table_count" -lt 10 ]]; then
  echo "FAIL: too few restored public tables" >&2
  exit 1
fi
migration_count="$(docker exec -u postgres "$name" psql -U postgres -d minefleet_restore_check -Atc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='alembic_version';")"
if [[ "$migration_count" != "1" ]]; then
  echo "FAIL: alembic_version is missing" >&2
  exit 1
fi
echo "PASS: isolated restore succeeded; tables=$table_count; alembic_version present."
echo "NOTICE: this smoke test is not a full disaster-recovery exercise or RPO/RTO certification."
