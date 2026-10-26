#!/bin/bash
# Amorçage PostgreSQL (super-utilisateur, hors Alembic) — MODELE_PHYSIQUE_LOT1.md §3.
# Exécuté une seule fois par l'image postgis à la création du volume.
# Les mots de passe viennent de l'environnement du conteneur (.env local), jamais du dépôt.
set -euo pipefail

: "${MF_OWNER_PASSWORD:?MF_OWNER_PASSWORD manquant}"
: "${MF_APP_PASSWORD:?MF_APP_PASSWORD manquant}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v owner_pw="$MF_OWNER_PASSWORD" -v app_pw="$MF_APP_PASSWORD" <<'SQL'
CREATE ROLE mf_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'owner_pw';
CREATE ROLE mf_app   LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT PASSWORD :'app_pw';
ALTER ROLE mf_app SET timezone = 'UTC';
ALTER ROLE mf_app SET search_path = public;
ALTER ROLE mf_owner SET timezone = 'UTC';
SQL

# Base applicative ; base de test seulement si demandée (dev/CI), jamais sur la démo (SEC-14).
databases="minefleet"
if [ "${MF_CREATE_TEST_DB:-false}" = "true" ]; then databases="minefleet minefleet_test"; fi
for db in $databases; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
    -c "CREATE DATABASE ${db} OWNER mf_owner"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<SQL
REVOKE ALL ON DATABASE ${db} FROM PUBLIC;
GRANT CONNECT ON DATABASE ${db} TO mf_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE SCHEMA app AUTHORIZATION mf_owner;
GRANT USAGE ON SCHEMA public, app TO mf_app;
GRANT SELECT ON spatial_ref_sys TO mf_app;
SQL
done
