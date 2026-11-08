#!/usr/bin/env bash
# Restore a MineFleet pg_dump archive into a disposable, network-isolated PostGIS instance.
# NEVER connects to or modifies the running production database.
set -euo pipefail
umask 077

if [[ $# -ne 1 && $# -ne 3 ]]; then
  echo "Usage: $0 /absolute/path/to/minefleet-YYYYMMDD.dump [--api-image IMAGE]" >&2
  exit 2
fi
api_image=""
if [[ $# -eq 3 ]]; then
  if [[ "$2" != "--api-image" || -z "$3" || ! "$3" =~ ^[A-Za-z0-9][A-Za-z0-9._/:@-]+$ ]]; then
    echo "FAIL: expected --api-image followed by a local Docker image reference" >&2
    exit 2
  fi
  api_image="$3"
fi
archive="$(realpath -- "$1")"
if [[ ! -f "$archive" || ! -s "$archive" ]]; then
  echo "FAIL: archive missing or empty" >&2
  exit 1
fi
command -v docker >/dev/null || { echo "FAIL: docker required" >&2; exit 1; }
name="minefleet-restore-check-${BASHPID}-${RANDOM}"
api_name="$name-api"
network_name="$name-net"
network_created=0
restore_failed=0
runtime_db_credential=""
runtime_signing_material=""
runtime_mfa_material=""
runtime_ratelimit_material=""

cleanup() {
  if [[ "$restore_failed" == "1" ]]; then
    if docker inspect "$api_name" >/dev/null 2>&1; then
      echo "MineFleet API container log (recovery smoke failed):" >&2
      docker logs "$api_name" >&2 || true
    fi
    echo "PostgreSQL container log (restore failed):" >&2
    docker logs "$name" >&2 || true
  fi
  docker rm -f "$api_name" >/dev/null 2>&1 || true
  docker rm -f "$name" >/dev/null 2>&1 || true
  if [[ "$network_created" == "1" ]]; then
    docker network rm "$network_name" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

db_network_args=(--network none)
if [[ -n "$api_image" ]]; then
  command -v openssl >/dev/null || { echo "FAIL: openssl required for API smoke secrets" >&2; exit 1; }
  if ! docker image inspect "$api_image" >/dev/null 2>&1; then
    echo "FAIL: API image is not available locally: $api_image" >&2
    exit 1
  fi
  docker network create --internal "$network_name" >/dev/null
  network_created=1
  db_network_args=(--network "$network_name" --network-alias restore-db)
  runtime_db_credential="$(openssl rand -hex 24)"
  runtime_signing_material="$(openssl rand -hex 48)"
  runtime_mfa_material="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n')"
  runtime_ratelimit_material="$(openssl rand -hex 48)"
fi

echo "Starting disposable PostGIS (isolated network, no persistent volumes)..."
docker run -d --rm --name "$name" "${db_network_args[@]}" \
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

# Do not relax the host archive permissions for Docker. Copy it into the disposable
# container, then make only the container's postgres user its private owner.
docker cp -- "$archive" "$name:/tmp/backup.dump"
docker exec -u root "$name" sh -c \
  'chown postgres:postgres /tmp/backup.dump && chmod 600 /tmp/backup.dump'

docker exec -u postgres "$name" createdb -U postgres minefleet_restore_check
# pg_dump archives contain ownership and ACL references, but not cluster roles.
# NOLOGIN roles are sufficient for a faithful isolated restore and cannot authenticate.
docker exec -u postgres "$name" psql -v ON_ERROR_STOP=1 -U postgres -d postgres \
  -c "CREATE ROLE mf_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS"
docker exec -u postgres "$name" psql -v ON_ERROR_STOP=1 -U postgres -d postgres \
  -c "CREATE ROLE mf_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT"
if [[ -n "$api_image" ]]; then
  docker exec -i -u postgres "$name" psql -v ON_ERROR_STOP=1 -U postgres -d postgres \
    -v app_pw="$runtime_db_credential" >/dev/null <<'SQL'
ALTER ROLE mf_app LOGIN PASSWORD :'app_pw';
SQL
fi
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
DO $verify$
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
$verify$;

BEGIN;
SET LOCAL ROLE mf_app;
DO $verify$
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
$verify$;
ROLLBACK;
SQL
then
  echo "FAIL: restored ownership, ACL or RLS validation failed" >&2
  restore_failed=1
  exit 1
fi

echo "PASS: isolated restore succeeded; tables=$table_count; ownership, ACLs and tenant RLS validated."

if [[ -n "$api_image" ]]; then
  echo "Starting the recovered API image on the private Docker network..."
  docker run -d --rm --name "$api_name" --network "$network_name" \
    --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m --tmpfs /data/mail:rw,noexec,nosuid,size=16m \
    --cap-drop ALL --security-opt no-new-privileges:true \
    -e MF_ENV=staging \
    -e MF_DB_HOST=restore-db -e MF_DB_PORT=5432 -e MF_DB_NAME=minefleet_restore_check \
    -e MF_APP_PASSWORD="$runtime_db_credential" -e MF_JWT_SECRET="$runtime_signing_material" \
    -e MF_MFA_ENCRYPTION_KEY="$runtime_mfa_material" -e MF_RATE_LIMIT_KEY="$runtime_ratelimit_material" -e MF_COOKIE_SECURE=true \
    -e MF_MAIL_BACKEND=capture -e MF_MAIL_CAPTURE_DIR=/data/mail \
    -e MF_PUBLIC_WEB_URL=https://staging.example.invalid \
    "$api_image" >/dev/null

  api_ready=0
  for _ in $(seq 1 60); do
    if [[ "$(docker inspect --format '{{.State.Running}}' "$api_name" 2>/dev/null || true)" != "true" ]]; then
      break
    fi
    if docker exec -i "$api_name" python - >/dev/null 2>&1 <<'PY'
import json
from urllib.request import urlopen

for route in ("/api/v1/health", "/api/v1/ready"):
    with urlopen(f"http://127.0.0.1:8000{route}", timeout=2) as response:
        assert response.status == 200
        assert json.load(response) == {"status": "ok"}
PY
    then
      api_ready=1
      break
    fi
    sleep 1
  done
  if [[ "$api_ready" != "1" ]]; then
    echo "FAIL: recovered API did not pass health and database readiness probes" >&2
    restore_failed=1
    exit 1
  fi
  echo "PASS: recovered API started with mf_app and passed /health and /ready."
fi

echo "NOTICE: this smoke test is not a full disaster-recovery exercise, staging restore or RPO/RTO certification."
