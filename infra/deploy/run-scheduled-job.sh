#!/usr/bin/env bash
# Lance une tâche planifiée MineFleet (unités systemd) dans un conteneur éphémère de l'image API
# RÉELLEMENT déployée, lue dans le reçu de release validé (release-state/current.json).
#
# Pourquoi : sans l'environnement de release, docker compose retombe sur MF_API_IMAGE par défaut
# (minefleet-api:local) et peut CONSTRUIRE une image depuis les sources — constat staging du
# 2026-11-16. Ici : reçu obligatoire, --no-build (échec plutôt que build), liste blanche des tâches.
#
# Usage : bash run-scheduled-job.sh {send-hse-digest|evaluate-preventive|sweep-gps-signal}
# Codes de sortie : code de la tâche · 2 configuration (tâche inconnue, reçu absent ou invalide).
set -euo pipefail
umask 077

cd "$(dirname "$0")"
job="${1:-}"
case "$job" in
  send-hse-digest|evaluate-preventive|sweep-gps-signal) ;;
  *)
    echo "Usage: $0 {send-hse-digest|evaluate-preventive|sweep-gps-signal}" >&2
    exit 2
    ;;
esac

state_directory="${MF_RELEASE_STATE_DIR:-release-state}"
receipt="$state_directory/current.json"
if [[ ! -f "$receipt" || -L "$receipt" ]]; then
  echo "FAIL: release receipt missing ($receipt) — deploy with staging-release.sh before scheduling jobs" >&2
  exit 2
fi
secrets_file="${MF_STAGING_SECRETS_FILE:-.env.prod}"
if [[ ! -f "$secrets_file" || -L "$secrets_file" ]]; then
  echo "FAIL: secret file missing or symlink: $secrets_file" >&2
  exit 2
fi

release_env="$(mktemp)"
trap 'rm -f -- "$release_env"' EXIT
if ! python3 release_manifest.py emit-release-env "$receipt" > "$release_env"; then
  echo "FAIL: release receipt is not a valid immutable manifest" >&2
  exit 2
fi

# Compose ne construit (section build:) ni ne tire une image déjà présente : exiger l'image déployée
# en local garantit que la tâche s'exécute sur le code de la release, jamais sur une image reconstruite.
api_image="$(sed -n 's/^MF_API_IMAGE=//p' "$release_env")"
if [[ ! "$api_image" =~ @sha256:[0-9a-f]{64}$ ]]; then
  echo "FAIL: release receipt did not yield a digest-pinned API image" >&2
  exit 2
fi
if ! docker image inspect "$api_image" >/dev/null 2>&1; then
  echo "FAIL: deployed API image is not present locally ($api_image) — refusing to let compose build or pull" >&2
  exit 2
fi

status=0
docker compose -f docker-compose.prod.yml --env-file "$secrets_file" --env-file "$release_env" \
  run --rm --no-deps api minefleet "$job" || status=$?
exit "$status"
