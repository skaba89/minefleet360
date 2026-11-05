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
restore_failed=0
cleanup() {
  if [[ "$restore_failed" == "1" ]]; then
    echo "PostgreSQL container log (restore failed):" >&2
    docker logs "$name" >&2 || true
  fi
  docker rm -f "$name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Starting disposable PostGIS (network disabled, no persistent volumes)..."
docker run -d --rm --name "$name" --network none \
  --mount "type=bind,source=$archive,target=/tmp/backup.dump,readonly" \
  -e POSTGRES_PASSWORD=throwaway-restore-only \
  postgis/postgis:16-3.4 >/dev/null

ready=0
for _ in $(seq 1 60); do
  # The PostGIS image briefly starts a temporary server while initializing extensions.
  # Wait for its init-complete marker before accepting pg_isready as final readiness.
  if docker logs "$name" 2>&1 | grep -Fq "PostgreSQL init process complete; ready for start up." \
    && docker exec "$name" pg_isready -U postgres >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" != "1" ]]; then
  echo "FAIL: isolated database did not start" >&2
  restore_failed=1
  exit 1
fi

docker exec -u postgres "$name" createdb -U postgres minefleet_restore_check
# pg_dump archives contain ownership and ACL references, but not cluster roles.
# NOLOGIN roles are sufficient for a faithful isolated restore and cannot authenticate.
docker exec -u postgres "$name" psql -v ON_ERROR_STOP=1 -U postgres -d postgres \
  -c "CREATE ROLE mf_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS"
docker exec -u postgres "$name" psql -v ON_ERROR_STOP=1 -U postgres -d postgres \
  -c "CREATE ROLE mf_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT"
# Restore ownership and ACLs. Omitting them would not prove that the API role can use the recovered schema.
if ! docker exec -u postgres "$name" pg_restore \
  --exit-on-error -U postgres \
  -d minefleet_restore_check /tmp/backup.dump >/dev/null; then
  echo "FAIL: pg_restore failed; collecting PostgreSQL diagnostics" >&2
  restore_failed=1
  exit 1
fi

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

# Prove that ownership, ACLs and the representative tenant RLS policy survived the restore.
if ! docker exec -i -u postgres "$name" psql -v ON_ERROR_STOP=1 -U postgres \
  -d minefleet_restore_check >/dev/null <<'SQL'
DO $
DECLARE
  restored_owner text;
  rls_enabled boolean;
  rls_forced boolean;
  app_policy_count integer;
BEGIN
  SELECT pg_get_userbyid(c.relowner), c.relrowsecurity, c.relforcerowsecurity
    INTO restored_owner, rls_enabled, rls_forced
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relname = 'tenant';

  IF restored_owner IS DISTINCT FROM 'mf_owner' THEN
    RAISE EXCEPTION 'tenant owner mismatch: %', restored_owner;
  END IF;
  IF NOT COALESCE(rls_enabled, false) OR NOT COALESCE(rls_forced, false) THEN
    RAISE EXCEPTION 'tenant RLS is not enabled and forced';
  END IF;

  SELECT count(*)
    INTO app_policy_count
    FROM pg_policy p
    JOIN pg_class c ON c.oid = p.polrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_roles r ON r.oid = ANY (p.polroles)
   WHERE n.nspname = 'public' AND c.relname = 'tenant' AND r.rolname = 'mf_app';

  IF app_policy_count < 1 THEN
    RAISE EXCEPTION 'tenant has no policy assigned to mf_app';
  END IF;
END
$;

BEGIN;
SET LOCAL ROLE mf_app;
DO $
DECLARE
  visible_tenants integer;
BEGIN
  PERFORM set_config('app.tenant_id', '', true);
  SELECT count(*) INTO visible_tenants FROM public.tenant;
  IF visible_tenants <> 0 THEN
    RAISE EXCEPTION 'RLS fail-closed check exposed % tenants', visible_tenants;
  END IF;

  PERFORM set_config('app.tenant_id', '00000000-0000-4000-8000-000000000001', true);
  SELECT count(*) INTO visible_tenants FROM public.tenant;
  IF visible_tenants < 1 THEN
    RAISE EXCEPTION 'mf_app cannot read the authorized platform tenant';
  END IF;
END
$;
ROLLBACK;
SQL
then
  echo "FAIL: restored ownership, ACL or RLS validation failed" >&2
  restore_failed=1
  exit 1
fi

echo "PASS: isolated restore succeeded; tables=$table_count; ownership, ACLs and tenant RLS validated."
echo "NOTICE: this smoke test is not a full disaster-recovery exercise, API startup test or RPO/RTO certification."
