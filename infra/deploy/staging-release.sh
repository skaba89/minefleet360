#!/usr/bin/env bash
# Reproducible staging release and application-only rollback using immutable images.
set -euo pipefail
umask 077

cd "$(dirname "$0")"
action="${1:-}"
manifest="${2:-}"
if [[ "$action" != "plan" && "$action" != "apply" && "$action" != "rollback" ]]; then
  echo "Usage: $0 {plan|apply|rollback} /absolute/path/release.json" >&2
  exit 2
fi
if [[ "$manifest" != /* || ! -f "$manifest" || -L "$manifest" ]]; then
  echo "FAIL: manifest must be an absolute regular non-symlink file" >&2
  exit 2
fi
for command in python3 docker stat mktemp; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "FAIL: required command missing: $command" >&2
    exit 2
  fi
done

python3 release_manifest.py validate "$manifest"
temporary="$(mktemp -d)"
trap 'rm -rf -- "$temporary"' EXIT
release_env="$temporary/release.env"
rollback_env="$temporary/rollback.env"
python3 release_manifest.py emit-release-env "$manifest" > "$release_env"
python3 release_manifest.py emit-rollback-env "$manifest" > "$rollback_env"
chmod 600 "$release_env" "$rollback_env"

release_commit="$(sed -n 's/^MF_RELEASE_COMMIT=//p' "$release_env")"
migration_head="$(sed -n 's/^MF_MIGRATION_HEAD=//p' "$release_env")"
rollback_commit="$(sed -n 's/^MF_RELEASE_COMMIT=//p' "$rollback_env")"
release_api_image="$(sed -n 's/^MF_API_IMAGE=//p' "$release_env")"
release_web_image="$(sed -n 's/^MF_WEB_IMAGE=//p' "$release_env")"
rollback_api_image="$(sed -n 's/^MF_API_IMAGE=//p' "$rollback_env")"
rollback_web_image="$(sed -n 's/^MF_WEB_IMAGE=//p' "$rollback_env")"
variant="$(sed -n 's/^MF_DEPLOYMENT_VARIANT=//p' "$release_env")"
if [[ ! "$release_commit" =~ ^[0-9a-f]{40}$ ]]; then
  echo "FAIL: validated manifest did not emit a release commit" >&2
  exit 2
fi

secrets_file="${MF_STAGING_SECRETS_FILE:-.env.prod}"
if [[ "$secrets_file" != /* ]]; then
  secrets_file="$(pwd)/$secrets_file"
fi
if [[ ! -f "$secrets_file" || -L "$secrets_file" ]]; then
  echo "FAIL: .env.prod must be a regular non-symlink staging secret file" >&2
  exit 2
fi
permissions="$(stat -c '%a' "$secrets_file")"
if [[ "$permissions" != "600" && "$permissions" != "400" ]]; then
  echo "FAIL: .env.prod permissions must be 600 or 400" >&2
  exit 2
fi
environment_lines="$(grep -Ec '^MF_ENV=' "$secrets_file" || true)"
secrets_environment="$(sed -n 's/^MF_ENV=//p' "$secrets_file")"
if [[ "$environment_lines" != "1" || "$secrets_environment" != "staging" ]]; then
  echo "FAIL: the protected secret file must contain exactly MF_ENV=staging" >&2
  exit 2
fi

compose_files=(-f docker-compose.prod.yml)
case "$variant" in
  edge) compose_files+=(-f docker-compose.edge.yml) ;;
  standalone) ;;
  *) echo "FAIL: unsupported deployment variant" >&2; exit 2 ;;
esac
selected_env="$release_env"
compose() {
  docker compose "${compose_files[@]}" --env-file "$secrets_file" --env-file "$selected_env" "$@"
}

# Read-only parse of the real staging configuration. --quiet prevents secret expansion in output.
compose config --quiet
if [[ "$action" == "plan" ]]; then
  echo "PLAN OK: staging release ${release_commit:0:12} uses immutable API/web images"
  echo "PLAN ONLY: no image pulled, container changed, migration run or backup created"
  exit 0
fi

expected_approval="${action}:${release_commit}"
if [[ "${MF_STAGING_CHANGE_APPROVAL:-}" != "$expected_approval" ]]; then
  echo "FAIL: set MF_STAGING_CHANGE_APPROVAL=$expected_approval for this staging action" >&2
  exit 2
fi
if [[ ! "${MINEFLEET_STAGING_URL:-}" =~ ^https://[a-zA-Z0-9._:-]+/?$ ]]; then
  echo "FAIL: MINEFLEET_STAGING_URL must be a credential-free HTTPS origin" >&2
  exit 2
fi

live_check() {
  MINEFLEET_STAGING_URL="$MINEFLEET_STAGING_URL" \
    bash check-preproduction.sh docker-compose.prod.yml --live
}

verify_image_commit() {
  local image="$1"
  local expected="$2"
  local observed
  observed="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$image")"
  if [[ "$observed" != "$expected" ]]; then
    echo "FAIL: immutable image revision label does not match the release manifest" >&2
    return 1
  fi
}

verify_api_migration_head() {
  local image="$1"
  local observed
  observed="$(docker image inspect --format '{{ index .Config.Labels "com.minefleet.alembic-head" }}' "$image")"
  if [[ "$observed" != "$migration_head" ]]; then
    echo "FAIL: API image migration label does not match the release manifest" >&2
    return 1
  fi
}

rollback_apps() {
  selected_env="$rollback_env"
  compose pull api web
  verify_image_commit "$rollback_api_image" "$rollback_commit"
  verify_image_commit "$rollback_web_image" "$rollback_commit"
  compose up -d --no-build api web
  live_check
}

if [[ "$action" == "rollback" ]]; then
  rollback_apps
  echo "ROLLBACK OK: application images reverted; database schema was not downgraded"
  exit 0
fi

# A release never starts without a new, readable PostgreSQL recovery point.
live_check
backup_directory="${MF_BACKUP_DIR:-backups}"
bash backup.sh
MF_BACKUP_DIR="$backup_directory" MF_BACKUP_MAX_AGE_HOURS=1 bash probe-backup-freshness.sh

compose pull api migrate web
verify_image_commit "$release_api_image" "$release_commit"
verify_image_commit "$release_web_image" "$release_commit"
verify_api_migration_head "$release_api_image"
compose up -d db
compose --profile ops run --rm --no-deps migrate
compose --profile ops run --rm --no-deps migrate python -m app.core.check_schema_revision
compose up -d --no-build api web

if ! live_check; then
  echo "FAIL: post-release smoke failed; attempting application-only rollback" >&2
  if rollback_apps; then
    echo "ROLLBACK OK: previous application images restored; schema kept forward" >&2
  else
    echo "CRITICAL: automatic application rollback also failed" >&2
  fi
  exit 1
fi

state_directory="${MF_RELEASE_STATE_DIR:-release-state}"
if [[ "$state_directory" != /* ]]; then
  state_directory="$(pwd)/$state_directory"
fi
if [[ -L "$state_directory" ]]; then
  echo "FAIL: release state directory must not be a symlink" >&2
  exit 1
fi
mkdir -p -- "$state_directory"
chmod 700 "$state_directory"
receipt="$state_directory/current.json"
receipt_partial="$receipt.partial"
cp -- "$manifest" "$receipt_partial"
chmod 600 "$receipt_partial"
mv -- "$receipt_partial" "$receipt"
echo "RELEASE OK: staging ${release_commit:0:12}; receipt stored without secrets"
