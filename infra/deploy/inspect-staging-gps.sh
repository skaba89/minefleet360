#!/usr/bin/env bash
# Inventory an existing MineFleet staging installation WITHOUT mutating its services.
# Run from the repository root on the VPS. Never print .env.prod or docker inspect Env.
set -euo pipefail
umask 077

cd "$(dirname "$0")/../.."
ROOT="$(pwd)"
DEPLOY="$ROOT/infra/deploy"
ENV_FILE="$DEPLOY/.env.prod"
COMPOSE="$DEPLOY/docker-compose.prod.yml"
EDGE="$DEPLOY/docker-compose.edge.yml"
EXPECTED_HEAD="0077"
EXPECTED_COMMIT="${MF_EXPECTED_MAIN_SHA:-}"

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || fail "Docker absent"
command -v git >/dev/null 2>&1 || fail "Git absent"
command -v curl >/dev/null 2>&1 || fail "curl absent"
[[ -f "$ENV_FILE" && ! -L "$ENV_FILE" ]] || fail "Fichier staging .env.prod absent/invalide"
[[ "$(grep -Ec '^MF_ENV=' "$ENV_FILE" || true)" == "1" ]] || fail "MF_ENV doit être présent une seule fois"
[[ "$(sed -n 's/^MF_ENV=//p' "$ENV_FILE")" == "staging" ]] || fail "Arrêt : cet outil est réservé à MF_ENV=staging"
[[ -f "$COMPOSE" && -f "$EDGE" ]] || fail "Fichiers Compose manquants"
if [[ -n "$EXPECTED_COMMIT" && ! "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
  fail "MF_EXPECTED_MAIN_SHA doit être un SHA Git complet"
fi

compose() {
  docker compose -f "$COMPOSE" -f "$EDGE" --env-file "$ENV_FILE" "$@"
}

echo "=== CODE LOCAL (ne prouve pas la version déployée) ==="
printf 'HEAD local: '; git rev-parse HEAD
printf 'Branche locale: '; git rev-parse --abbrev-ref HEAD
if [[ -n "$EXPECTED_COMMIT" ]]; then
  printf 'Commit cible de recette: %s\n' "$EXPECTED_COMMIT"
fi
echo "=== COMPOSE (lecture seule) ==="
compose config --quiet
echo "Configuration Compose valide"
echo "=== SERVICES EN COURS ==="
compose ps --format 'table {{.Service}}\t{{.State}}\t{{.Image}}'
echo "=== IDENTITÉ DES IMAGES DEPUIS LES CONTENEURS ==="
for service in api web; do
  container="$(compose ps -q "$service")"
  if [[ -z "$container" ]]; then
    printf '%s: ABSENT\n' "$service"
    continue
  fi
  image_id="$(docker container inspect --format '{{.Image}}' "$container")"
  revision="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image_id")"
  printf '%s: image_id=%s git_revision=%s\n' "$service" "$image_id" "$revision"
  if [[ -n "$EXPECTED_COMMIT" && "$revision" != "$EXPECTED_COMMIT" ]]; then
    printf '%s: DIVERGENCE avec le commit cible\n' "$service"
  fi
  if [[ "$service" == "api" ]]; then
    migration_label="$(docker image inspect --format '{{index .Config.Labels "com.minefleet.alembic-head"}}' "$image_id")"
    printf 'api: migration_head_image=%s\n' "$migration_label"
  fi
done
echo "=== RÉVISION ALEMBIC (SELECT UNIQUEMENT) ==="
db_container="$(compose ps -q db)"
if [[ -z "$db_container" ]]; then
  echo "DB absente : révision non vérifiable"
else
  # Password stays inside the container; never output its environment.
  if ! revision="$(docker exec "$db_container" sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -A -t -q -v ON_ERROR_STOP=1 -U postgres -d minefleet -c "SELECT version_num FROM alembic_version ORDER BY version_num;"' 2>/dev/null)"; then
    echo "Lecture SQL indisponible : ne pas inférer la migration"
  else
    printf 'Révision(s) en base: %s\n' "$revision"
    if [[ "$revision" != "$EXPECTED_HEAD" ]]; then
      printf 'ÉCART : la migration attendue dans main est %s ; aucune migration exécutée.\n' "$EXPECTED_HEAD"
    fi
  fi
fi

echo "=== HTTPS (aucun corps/secret collecté) ==="
ORIGIN="${MINEFLEET_STAGING_URL:-https://minefleet.51-75-248-4.sslip.io}"
[[ "$ORIGIN" =~ ^https://[A-Za-z0-9._:-]+/?$ ]] || fail "URL de recette HTTPS invalide"
ORIGIN="${ORIGIN%/}"
for path in / /api/v1/health /api/v1/ready /fleet-icons.svg; do
  code="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' --connect-timeout 5 --max-time 12 --proto '=https' "$ORIGIN$path" || true)"
  printf '%s -> HTTP %s\n' "$path" "$code"
done
echo "=== FIN INVENTAIRE ==="
echo "Lecture seule. Aucune migration, aucun redémarrage, aucun pull et aucun déploiement."
