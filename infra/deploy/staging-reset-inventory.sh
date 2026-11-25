#!/usr/bin/env bash
# Inventory-only step for issue #532.
# No writes: no SQL DML/DDL, no Docker volume operations, no service restarts.
set -euo pipefail
umask 077

deploy_dir="${MF_DEPLOY_DIR:-/opt/minefleet/infra/deploy}"
env_file="$deploy_dir/.env.prod"
db_container="${MF_DB_CONTAINER:-minefleet-db-1}"

if [[ ! -f "$env_file" ]]; then
  echo "REFUS: staging environment file missing" >&2
  exit 2
fi
if ! grep -Eq '^[[:space:]]*MF_ENV=staging[[:space:]]*$' "$env_file"; then
  echo "REFUS: MF_ENV=staging not explicitly confirmed" >&2
  exit 2
fi
if [[ "$db_container" != "minefleet-db-1" ]]; then
  echo "REFUS: only the expected MineFleet staging database container is permitted" >&2
  exit 2
fi
if ! docker inspect -f '{{.State.Running}}' "$db_container" 2>/dev/null | grep -qx true; then
  echo "REFUS: MineFleet staging database container is not running" >&2
  exit 2
fi

echo "=== MineFleet staging: inventaire sans modification ==="
echo "NOTE: catalog estimates are approximate, not actual row counts."
echo "NOTE: reference classification requires review of seed code/migrations."
docker exec -i "$db_container" sh -ec '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  exec psql -X -v ON_ERROR_STOP=1 -P pager=off -U postgres -d minefleet
' <<'SQL'
BEGIN READ ONLY;

SELECT current_database() AS database_name,
       current_setting('server_version') AS pg_version;

SELECT version_num AS alembic_version FROM public.alembic_version;

SELECT c.relname AS table_name,
       CASE c.relkind WHEN 'p' THEN 'partitioned_parent'
                      WHEN 'r' THEN CASE WHEN c.relispartition THEN 'partition_child'
                                        ELSE 'ordinary' END
                      ELSE c.relkind::text END AS relation_kind,
       COALESCE(c.reltuples::bigint, 0) AS estimated_rows,
       c.relrowsecurity AS rls_enabled,
       c.relforcerowsecurity AS rls_forced,
       EXISTS (
         SELECT 1 FROM pg_attribute a
          WHERE a.attrelid = c.oid AND a.attname = 'tenant_id'
            AND a.attnum > 0 AND NOT a.attisdropped
       ) AS has_tenant_id,
       CASE
         WHEN c.relname IN ('alembic_version','spatial_ref_sys')
           THEN 'PROTECT_TECHNICAL'
         WHEN c.relname IN ('role','role_allowed_scope','saas_plan')
           THEN 'REVIEW_GLOBAL_REFERENCE'
         WHEN c.relispartition THEN 'REVIEW_PARTITION_CHILD'
         ELSE 'REVIEW_SCHEMA_AND_DEPENDENCIES'
       END AS review_category
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind IN ('r','p')
 ORDER BY review_category, c.relname;

SELECT con.conname AS fk_name,
       con.conrelid::regclass::text AS referencing_table,
       con.confrelid::regclass::text AS referenced_table,
       pg_get_constraintdef(con.oid) AS constraint_definition
  FROM pg_constraint con
 WHERE con.contype = 'f'
   AND con.connamespace = 'public'::regnamespace
 ORDER BY referencing_table, referenced_table, fk_name;

SELECT parent.relname AS parent_table,
       child.relname AS child_partition
  FROM pg_inherits i
  JOIN pg_class parent ON parent.oid = i.inhparent
  JOIN pg_class child ON child.oid = i.inhrelid
  JOIN pg_namespace n ON n.oid = child.relnamespace
 WHERE n.nspname = 'public'
 ORDER BY parent.relname, child.relname;

SELECT 'tenant' AS entity, count(*) AS rows FROM public.tenant
UNION ALL
SELECT 'user_account', count(*) FROM public.user_account
UNION ALL
SELECT 'user_role_assignment', count(*) FROM public.user_role_assignment
UNION ALL
SELECT 'auth_session', count(*) FROM public.auth_session
UNION ALL
SELECT 'account_token', count(*) FROM public.account_token
ORDER BY entity;

ROLLBACK;
SQL
echo "PASS: inventory only; no data or schema changed."
