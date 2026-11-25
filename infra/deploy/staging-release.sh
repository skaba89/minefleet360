#!/usr/bin/env bash
# Reproducible staging release and application-only rollback using immutable images.
#
#   plan | apply | rollback                     signed GHCR images only (Cosign + SLSA verified)
#   plan-fallback | rollback-fallback           exact local archives, UNSIGNED, separate manifest
#
# Invariants (tests/test_ops_staging_release.py): PostgreSQL is never started, stopped,
# recreated or downgraded by this script; only the api/web containers are replaced, with
# --no-deps; their volumes, networks, ports, security settings and the read-only PMTiles
# mount are compared before and after.
set -euo pipefail
umask 077

cd "$(dirname "$0")"
action="${1:-}"
manifest="${2:-}"
case "$action" in
  plan|apply|rollback) fallback=0 ;;
  plan-fallback|rollback-fallback) fallback=1 ;;
  *)
    echo "Usage: $0 {plan|apply|rollback|plan-fallback|rollback-fallback} /absolute/path/manifest.json" >&2
    exit 2
    ;;
esac
if [[ "$manifest" != /* || ! -f "$manifest" || -L "$manifest" ]]; then
  echo "FAIL: manifest must be an absolute regular non-symlink file" >&2
  exit 2
fi
required_commands=(python3 docker stat mktemp curl sha256sum)
if (( fallback == 0 )); then
  required_commands+=(cosign)
fi
for command in "${required_commands[@]}"; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "FAIL: required command missing: $command" >&2
    exit 2
  fi
done

temporary="$(mktemp -d)"
trap 'rm -rf -- "$temporary"' EXIT
release_env="$temporary/release.env"
rollback_env="$temporary/rollback.env"
if (( fallback == 0 )); then
  python3 release_manifest.py validate "$manifest"
  python3 release_manifest.py emit-release-env "$manifest" > "$release_env"
  python3 release_manifest.py emit-rollback-env "$manifest" > "$rollback_env"
else
  python3 release_manifest.py validate-fallback "$manifest"
  echo "WARNING: local fallback images are UNSIGNED local artifacts, not GHCR releases"
  # The fallback has no forward release: its only target is the rollback.
  python3 release_manifest.py emit-fallback-env "$manifest" > "$rollback_env"
  cp -- "$rollback_env" "$release_env"
fi
chmod 600 "$release_env" "$rollback_env"

env_value() { sed -n "s/^$2=//p" "$1"; }
release_commit="$(env_value "$release_env" MF_RELEASE_COMMIT)"
migration_head="$(env_value "$release_env" MF_MIGRATION_HEAD)"
rollback_api_commit="$(env_value "$rollback_env" MF_API_COMMIT)"
rollback_web_commit="$(env_value "$rollback_env" MF_WEB_COMMIT)"
rollback_api_head="$(env_value "$rollback_env" MF_API_MIGRATION_HEAD)"
variant="$(env_value "$release_env" MF_DEPLOYMENT_VARIANT)"
if (( fallback == 0 )) && [[ ! "$release_commit" =~ ^[0-9a-f]{40}$ ]]; then
  echo "FAIL: validated manifest did not emit a release commit" >&2
  exit 2
fi
if [[ ! "$rollback_api_commit" =~ ^[0-9a-f]{40}$ || ! "$rollback_web_commit" =~ ^[0-9a-f]{40}$ ]]; then
  echo "FAIL: validated manifest did not emit complete API/web rollback commits" >&2
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
compose_project="minefleet"
configured_db_volume="$(sed -n 's/^MF_DB_VOLUME=//p' "$secrets_file")"
expected_db_volume="${MF_EXPECTED_DB_VOLUME:-${configured_db_volume:-${compose_project}_db-data}}"

# Read-only parse of the real staging configuration. --quiet prevents secret expansion in output.
compose config --quiet

# ---------------------------------------------------------------------------------------
# Read-only preflight shared by every action (plan included): provenance, PostgreSQL,
# runtime configuration of api/web and PMTiles basemap. Nothing is pulled or started here.
# ---------------------------------------------------------------------------------------
cosign_identity='^https://github\.com/skaba89/minefleet360/\.github/workflows/release-images\.yml@refs/(heads/main|tags/v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?)$'
cosign_issuer='https://token.actions.githubusercontent.com'
verify_provenance() {
  local image="$1"
  if ! cosign verify --certificate-oidc-issuer "$cosign_issuer" \
      --certificate-identity-regexp "$cosign_identity" "$image" >/dev/null 2>&1; then
    echo "FAIL: Cosign signature not verified for $image" >&2
    return 1
  fi
  if ! cosign verify-attestation --type https://slsa.dev/provenance/v1 \
      --certificate-oidc-issuer "$cosign_issuer" \
      --certificate-identity-regexp "$cosign_identity" "$image" >/dev/null 2>&1; then
    echo "FAIL: SLSA v1 provenance attestation not verified for $image" >&2
    return 1
  fi
  echo "OK: signature and SLSA provenance verified for ${image##*@sha256:}" | cut -c1-80
}

database_identity() {
  local ids
  ids="$(compose ps -q db)"
  if [[ -z "$ids" || "$ids" == *$'\n'* ]]; then
    echo "FAIL: exactly one running PostgreSQL container is required; this script never starts it" >&2
    return 1
  fi
  docker inspect "$ids" > "$temporary/db.inspect.json"
  python3 runtime_guard.py database "$temporary/db.inspect.json" \
    --project "$compose_project" --volume "$expected_db_volume"
}

database_revision() {
  # Read-only query of alembic_version through the running database container.
  compose exec -T db psql -U postgres -d minefleet -AtX \
    -c 'SELECT version_num FROM alembic_version ORDER BY 1' </dev/null | tr '\n' ' ' | sed 's/ $//'
}

runtime_snapshot() {
  local output="$1" ids
  ids="$(compose ps -q api web)"
  if [[ -z "$ids" ]]; then
    echo "FAIL: running api/web containers are required to preserve their configuration" >&2
    return 1
  fi
  # shellcheck disable=SC2086 # container IDs are hexadecimal words
  docker inspect $ids > "$temporary/apps.inspect.json"
  python3 runtime_guard.py snapshot "$temporary/apps.inspect.json" --project "$compose_project" > "$output"
}

basemap_listing() {
  local directory="$1"
  find "$directory" -maxdepth 1 -type f -name '*.pmtiles' -printf '%f %s\n' | sort
}

running_image_matches() {
  local service="$1" reference="$2" running expected
  running="$(docker inspect --format '{{.Image}}' "$(compose ps -q "$service")")"
  expected="$(docker image inspect --format '{{.Id}}' "$reference")"
  if [[ -z "$running" || "$running" != "$expected" ]]; then
    echo "FAIL: running $service container does not use the verified image" >&2
    return 1
  fi
}

verify_image_labels() {
  local image="$1" expected_commit="$2" expected_head="${3:-}" observed
  observed="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$image")"
  if [[ "$observed" != "$expected_commit" ]]; then
    echo "FAIL: image revision label does not match the manifest commit" >&2
    return 1
  fi
  if [[ -n "$expected_head" ]]; then
    observed="$(docker image inspect --format '{{ index .Config.Labels "com.minefleet.alembic-head" }}' "$image")"
    if [[ "$observed" != "$expected_head" ]]; then
      echo "FAIL: API image migration label does not match the manifest" >&2
      return 1
    fi
  fi
}

if (( fallback == 0 )); then
  for image in \
      "$(env_value "$release_env" MF_API_IMAGE)" "$(env_value "$release_env" MF_WEB_IMAGE)" \
      "$(env_value "$rollback_env" MF_API_IMAGE)" "$(env_value "$rollback_env" MF_WEB_IMAGE)"; do
    verify_provenance "$image"
  done
else
  for component in api web; do
    upper="${component^^}"
    archive="$(env_value "$rollback_env" "MF_${upper}_ARCHIVE")"
    if [[ ! -f "$archive" || -L "$archive" ]]; then
      echo "FAIL: $component fallback archive must be a regular non-symlink file" >&2
      exit 2
    fi
    python3 release_manifest.py check-archive "$manifest" "$component" > "$temporary/$component.archive"
    echo "OK: $component archive SHA256 and image ID match the fallback manifest"
  done
fi

db_info="$(database_identity)"
read -r db_container db_started <<< "$db_info"
echo "OK: PostgreSQL ${db_container:0:12} running, healthy, volume $expected_db_volume"
db_revision_before="$(database_revision)"
if [[ "$db_revision_before" != "$migration_head" && "$db_revision_before" != "$rollback_api_head" ]]; then
  echo "FAIL: database revision is neither the forward head nor the rollback API head" >&2
  exit 2
fi
echo "OK: database Alembic revision $db_revision_before"

runtime_snapshot "$temporary/runtime.before.json"
compose config --format json > "$temporary/compose.json"
python3 runtime_guard.py expected "$temporary/compose.json" > "$temporary/runtime.planned.json"
rm -f -- "$temporary/compose.json"
basemap_source="$(python3 -c 'import json,sys
m=[x for x in json.load(open(sys.argv[1]))["web"]["mounts"] if "->/srv/basemap:" in x]
print(m[0].split(":",1)[1].split("->",1)[0] if len(m)==1 else "")' "$temporary/runtime.before.json")"
if [[ -z "$basemap_source" || ! -d "$basemap_source" ]]; then
  echo "FAIL: running web container has no readable PMTiles basemap directory" >&2
  exit 2
fi
python3 runtime_guard.py compare "$temporary/runtime.before.json" "$temporary/runtime.planned.json" \
  --basemap "$basemap_source"
basemap_listing "$basemap_source" > "$temporary/basemap.before"
if [[ ! -s "$temporary/basemap.before" ]]; then
  echo "FAIL: no PMTiles file found in the basemap directory" >&2
  exit 2
fi
echo "OK: PMTiles basemap $(tr '\n' ' ' < "$temporary/basemap.before")"

if [[ "$action" == plan* ]]; then
  echo "PLAN OK: ${action} validated; PostgreSQL will not be touched"
  echo "PLAN ONLY: no image pulled, container changed, migration run or backup created"
  exit 0
fi

# ---------------------------------------------------------------------------------------
# Mutating actions.
# ---------------------------------------------------------------------------------------
if (( fallback == 0 )); then
  expected_approval="${action}:${release_commit}"
else
  expected_approval="${action}:${rollback_api_commit}:${rollback_web_commit}"
fi
if [[ "${MF_STAGING_CHANGE_APPROVAL:-}" != "$expected_approval" ]]; then
  echo "FAIL: set MF_STAGING_CHANGE_APPROVAL=$expected_approval for this staging action" >&2
  exit 2
fi
if [[ ! "${MINEFLEET_STAGING_URL:-}" =~ ^https://[a-zA-Z0-9._:-]+/?$ ]]; then
  echo "FAIL: MINEFLEET_STAGING_URL must be a credential-free HTTPS origin" >&2
  exit 2
fi
smoke_credentials="${MF_SMOKE_CREDENTIALS_FILE:-}"
if [[ "$smoke_credentials" != /* || ! -f "$smoke_credentials" || -L "$smoke_credentials" ]] \
    || [[ "$(stat -c '%a' "$smoke_credentials")" != "600" && "$(stat -c '%a' "$smoke_credentials")" != "400" ]]; then
  echo "FAIL: MF_SMOKE_CREDENTIALS_FILE must be an absolute 600/400 file (fictitious staging account)" >&2
  exit 2
fi
# Content checked before any mutation (staging 2026-11-24: an empty file only failed after the swap).
MF_SMOKE_CREDENTIALS_FILE="$smoke_credentials" python3 business-smoke.py --check-credentials || exit 2

live_check() {
  MINEFLEET_STAGING_URL="$MINEFLEET_STAGING_URL" \
    bash check-preproduction.sh docker-compose.prod.yml --live
}

# After `up -d` the API needs a few seconds before uvicorn serves requests: the edge proxy answers
# 502 meanwhile (observed on staging 2026-11-16, release and rollback both failed on a transient 502).
# Poll /api/v1/ready within a bounded window, then run the unchanged smoke gate.
ready_timeout="${MF_RELEASE_READY_TIMEOUT:-120}"
ready_interval="${MF_RELEASE_READY_INTERVAL:-3}"
if [[ ! "$ready_timeout" =~ ^[0-9]+$ ]] || (( ready_timeout < 1 || ready_timeout > 600 )); then
  echo "FAIL: MF_RELEASE_READY_TIMEOUT must be an integer between 1 and 600 seconds" >&2
  exit 2
fi
if [[ ! "$ready_interval" =~ ^[0-9]+$ ]] || (( ready_interval > 30 )); then
  echo "FAIL: MF_RELEASE_READY_INTERVAL must be an integer between 0 and 30 seconds" >&2
  exit 2
fi

wait_until_ready() {
  local base="${MINEFLEET_STAGING_URL%/}"
  local deadline=$((SECONDS + ready_timeout))
  local code
  while (( SECONDS < deadline )); do
    code="$(curl --silent --output /dev/null --write-out '%{http_code}' \
      --connect-timeout 3 --max-time 5 --proto '=https' "$base/api/v1/ready" 2>/dev/null || true)"
    if [[ "$code" == "200" ]]; then
      echo "OK: API ready after restart"
      return 0
    fi
    sleep "$ready_interval"
  done
  echo "FAIL: API not ready within ${ready_timeout}s after restart (last HTTP ${code:-none})" >&2
  return 1
}

# Everything that must hold after api/web were replaced, whichever version now runs.
post_start_check() {
  local env_file="$1" expected_revision="$2"
  wait_until_ready || return 1
  live_check || return 1
  MINEFLEET_STAGING_URL="$MINEFLEET_STAGING_URL" MF_SMOKE_CREDENTIALS_FILE="$smoke_credentials" \
    python3 business-smoke.py || return 1
  local now_info now_container now_started
  now_info="$(database_identity)" || return 1
  read -r now_container now_started <<< "$now_info"
  if [[ "$now_container" != "$db_container" || "$now_started" != "$db_started" ]]; then
    echo "CRITICAL: PostgreSQL container was recreated or restarted" >&2
    return 1
  fi
  if [[ "$(database_revision)" != "$expected_revision" ]]; then
    echo "FAIL: database Alembic revision changed unexpectedly" >&2
    return 1
  fi
  runtime_snapshot "$temporary/runtime.after.json" || return 1
  python3 runtime_guard.py compare "$temporary/runtime.before.json" "$temporary/runtime.after.json" \
    --basemap "$basemap_source" || return 1
  basemap_listing "$basemap_source" > "$temporary/basemap.after"
  if ! cmp -s "$temporary/basemap.before" "$temporary/basemap.after"; then
    echo "FAIL: PMTiles basemap files changed during the intervention" >&2
    return 1
  fi
  running_image_matches api "$(env_value "$env_file" MF_API_IMAGE)" || return 1
  running_image_matches web "$(env_value "$env_file" MF_WEB_IMAGE)" || return 1
  echo "OK: PostgreSQL untouched (${now_container:0:12}), revision $expected_revision, runtime preserved"
}

# Replace only api/web: --no-deps keeps Compose from touching PostgreSQL, --pull never runs
# exactly the images verified above.
replace_apps() {
  compose up -d --no-deps --no-build --pull never api web
}

prepare_signed_rollback() {
  selected_env="$rollback_env"
  compose pull api web
  verify_image_labels "$(env_value "$rollback_env" MF_API_IMAGE)" "$rollback_api_commit" "$rollback_api_head"
  verify_image_labels "$(env_value "$rollback_env" MF_WEB_IMAGE)" "$rollback_web_commit"
  selected_env="$release_env"
}

prepare_fallback_images() {
  local component upper image_id tag commit
  for component in api web; do
    upper="${component^^}"
    image_id="$(env_value "$rollback_env" "MF_${upper}_IMAGE_ID")"
    tag="$(env_value "$rollback_env" "MF_${upper}_IMAGE")"
    commit="$(env_value "$rollback_env" "MF_${upper}_COMMIT")"
    if ! docker image inspect "$image_id" >/dev/null 2>&1; then
      if grep -q '^REGISTRY_TAGS=yes' "$temporary/$component.archive"; then
        echo "FAIL: $component archive carries registry tags; loading it would label an unsigned image as a registry artifact" >&2
        return 1
      fi
      docker load --input "$(env_value "$rollback_env" "MF_${upper}_ARCHIVE")" >/dev/null
    fi
    docker tag "$image_id" "$tag"
    if [[ "$(docker image inspect --format '{{.Id}}' "$tag")" != "$image_id" ]]; then
      echo "FAIL: $component local fallback tag does not resolve to the declared image ID" >&2
      return 1
    fi
    if [[ "$component" == api ]]; then
      verify_image_labels "$tag" "$commit" "$rollback_api_head"
    else
      verify_image_labels "$tag" "$commit"
    fi
  done
}

backup_database() {
  backup_directory="${MF_BACKUP_DIR:-backups}"
  # A release never deletes existing recovery points: retention stays with the daily job.
  MF_BACKUP_SKIP_RETENTION=1 bash backup.sh
  MF_BACKUP_DIR="$backup_directory" MF_BACKUP_MAX_AGE_HOURS=1 bash probe-backup-freshness.sh
}

rollback_apps() {
  local label="$1" expected_revision="$2"
  selected_env="$rollback_env"
  replace_apps
  if post_start_check "$rollback_env" "$expected_revision"; then
    echo "ROLLBACK OK ($label): api ${rollback_api_commit:0:12}, web ${rollback_web_commit:0:12}; database schema was not downgraded"
    return 0
  fi
  return 1
}

if [[ "$action" == rollback || "$action" == rollback-fallback ]]; then
  live_check || echo "WARNING: pre-rollback live check failed; continuing with the rollback" >&2
  backup_database
  if [[ "$action" == rollback ]]; then
    prepare_signed_rollback
    rollback_apps "signed GHCR images" "$db_revision_before"
  else
    prepare_fallback_images
    rollback_apps "UNSIGNED local fallback images" "$db_revision_before"
  fi
  exit $?
fi

# apply: a release never starts without a healthy target and a new, readable recovery point.
live_check
# Baseline: the business paths must already work on the running version (proves credentials too).
MINEFLEET_STAGING_URL="$MINEFLEET_STAGING_URL" MF_SMOKE_CREDENTIALS_FILE="$smoke_credentials"   python3 business-smoke.py
backup_database

selected_env="$release_env"
compose pull api migrate web
verify_image_labels "$(env_value "$release_env" MF_API_IMAGE)" "$release_commit" "$migration_head"
verify_image_labels "$(env_value "$release_env" MF_WEB_IMAGE)" "$release_commit"
# The rollback images are fetched and checked before the schema moves forward.
prepare_signed_rollback
selected_env="$release_env"
compose --profile ops run --rm --no-deps migrate
compose --profile ops run --rm --no-deps migrate python -m app.core.check_schema_revision
replace_apps

if ! post_start_check "$release_env" "$migration_head"; then
  echo "FAIL: post-release checks failed; attempting application-only rollback" >&2
  if rollback_apps "automatic, signed GHCR images" "$migration_head" >&2; then
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
