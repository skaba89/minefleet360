#!/usr/bin/env bash
# Staging reset by NEW candidate database (#532). The running database is never cleaned in place.
#
#   plan                               (default) read-only checks and the exact approval strings
#   build-candidate                    new isolated Compose project + new volume, Alembic migrations with
#                                      the running API image, reference tables copied, full comparison
#   bootstrap-candidate <project>      minefleet create-platform-admin on the candidate, real login + MFA
#   cutover <project>                  backup, then point the staging `db` service at the candidate volume
#   rollback-cutover <project>         point `db` back at the previous volume (kept intact) and prove it
#
# Never: DROP DATABASE, TRUNCATE, DELETE on the running database, `compose down`, volume removal,
# trigger or RLS disabling on the running database. See docs/ops/STAGING_RESET.md.
set -euo pipefail
umask 077
cd "$(dirname "$0")"
deploy_dir="$(pwd)"

action="${1:-plan}"
candidate="${2:-}"
case "$action" in
  plan|build-candidate) ;;
  bootstrap-candidate|cutover|rollback-cutover)
    if [[ ! "$candidate" =~ ^minefleet-reset-[0-9]{8}t[0-9]{6}z$ ]]; then
      echo "FAIL: $action requires a candidate project name minefleet-reset-<YYYYMMDD>t<HHMMSS>z" >&2
      exit 2
    fi
    ;;
  *) echo "Usage: $0 [plan|build-candidate|bootstrap-candidate P|cutover P|rollback-cutover P]" >&2; exit 2 ;;
esac
for command in docker python3 stat mktemp sha256sum hostname; do
  command -v "$command" >/dev/null 2>&1 || { echo "FAIL: required command missing: $command" >&2; exit 2; }
done

live_project="minefleet"
live_db_name="minefleet-db-1"
secrets_file="${MF_STAGING_SECRETS_FILE:-$deploy_dir/.env.prod}"
state_root="$deploy_dir/release-state/reset"
temporary="$(mktemp -d)"
stop_on_exit=()   # containers to stop if a step aborts (never volumes)
cleanup() {
  local item
  for item in "${stop_on_exit[@]}"; do docker stop "$item" >/dev/null 2>&1 || true; done
  rm -rf -- "$temporary"
}
trap cleanup EXIT

fail() { echo "FAIL: $*" >&2; [[ -n "${evidence:-}" ]] && echo "$(date -u +%FT%TZ) FAIL: $*" >> "$evidence"; exit 1; }
note() { echo "$*"; [[ -n "${evidence:-}" ]] && echo "$(date -u +%FT%TZ) $*" >> "$evidence"; return 0; }

# --- Environment identification: staging only, explicit host, protected secrets file -----------
[[ -f "$secrets_file" && ! -L "$secrets_file" ]] || { echo "FAIL: .env.prod must be a regular file" >&2; exit 2; }
[[ "$(stat -c '%a' "$secrets_file")" =~ ^[46]00$ ]] || { echo "FAIL: .env.prod must be mode 600 or 400" >&2; exit 2; }
if [[ "$(grep -c '^MF_ENV=' "$secrets_file")" != 1 || "$(sed -n 's/^MF_ENV=//p' "$secrets_file")" != staging ]]; then
  echo "FAIL: refused: the secrets file must contain exactly MF_ENV=staging (production and unidentified environments are refused)" >&2
  exit 2
fi
if [[ -z "${MF_RESET_EXPECTED_HOST:-}" || "$MF_RESET_EXPECTED_HOST" != "$(hostname)" ]]; then
  echo "FAIL: refused: set MF_RESET_EXPECTED_HOST to this host's name to confirm the target ($(hostname))" >&2
  exit 2
fi

live_volume="$(sed -n 's/^MF_DB_VOLUME=//p' "$secrets_file")"
live_volume="${live_volume:-minefleet_db-data}"
compose_live() {
  docker compose -p "$live_project" -f docker-compose.prod.yml -f docker-compose.edge.yml --env-file "$secrets_file" "$@"
}

# --- Running database identity -----------------------------------------------------------------
live_db="$(compose_live ps -q db)"
[[ -n "$live_db" && "$live_db" != *$'\n'* ]] || { echo "FAIL: exactly one running staging db container is required" >&2; exit 2; }
db_name="$(docker inspect -f '{{.Name}}' "$live_db")"
[[ "$db_name" == "/$live_db_name" ]] || { echo "FAIL: unexpected staging db container $db_name" >&2; exit 2; }
docker inspect "$live_db" > "$temporary/db.json"
python3 runtime_guard.py database "$temporary/db.json" --project "$live_project" --volume "$live_volume" > "$temporary/db.id" \
  || { echo "FAIL: staging database not running/healthy on volume $live_volume" >&2; exit 2; }
read -r live_db_id _ < "$temporary/db.id"
live_api="$(compose_live ps -q api)"
[[ -n "$live_api" ]] || { echo "FAIL: running api container required (its image builds the candidate)" >&2; exit 2; }
api_image="$(docker inspect -f '{{.Config.Image}}' "$live_api")"

catalog() {  # catalog <container> <output>
  docker exec -i "$1" psql -X -q -U postgres -d minefleet < staging-reset-catalog.sql > "$2"
  grep -q '^platform_tenant|' "$2" || fail "catalog extraction incomplete for $1"
}

if [[ "$action" == plan ]]; then
  catalog "$live_db" "$temporary/live.catalog"
  echo "== MineFleet staging reset: PLAN (read-only, nothing changed)"
  echo "host: $(hostname)  env: staging  live db: ${live_db_id:0:12} volume: $live_volume"
  echo "api image used for migrations: ${api_image##*@}"
  echo "alembic: $(sed -n 's/^alembic|head|//p' "$temporary/live.catalog")"
  echo "tables: $(grep -c '^rows|' "$temporary/live.catalog")  partitions: $(grep -c '^partition|' "$temporary/live.catalog")"
  echo "non-empty tables: $(grep '^rows|' "$temporary/live.catalog" | awk -F'|' '$3>0' | wc -l)"
  echo "reference tables (rows:digest):"; sed -n 's/^ref|/  /p' "$temporary/live.catalog"
  echo "next: MF_RESET_APPROVAL=build-candidate:${live_db_id:0:12}:$live_volume $0 build-candidate"
  exit 0
fi

# --- Candidate helpers -------------------------------------------------------------------------
candidate_env() {  # never mounts the running volume: MF_DB_VOLUME is forced for the candidate
  printf 'MF_DB_VOLUME=%s_db-data\nMF_API_IMAGE=%s\n' "$1" "$api_image" > "$temporary/candidate.env"
}
compose_candidate() {
  docker compose -p "$candidate" -f docker-compose.prod.yml --env-file "$secrets_file" \
    --env-file "$temporary/candidate.env" "$@"
}
candidate_volume_resolved() {  # before any `up`: Compose must resolve db-data to the candidate volume
  local resolved
  resolved="$(compose_candidate config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["volumes"]["db-data"]["name"])')"
  [[ "$resolved" == "${candidate}_db-data" && "$resolved" != "$live_volume" ]] \
    || fail "candidate Compose project resolves db-data to $resolved; refusing to start it"
}
wait_healthy() {
  local id="$1"
  for _ in $(seq 90); do
    [[ "$(docker inspect -f '{{.State.Health.Status}}' "$id" 2>/dev/null)" == healthy ]] && return 0
    sleep 2
  done
  fail "database $id did not become healthy"
}
candidate_db_mount_check() {
  local id="$1" expected="$2" mounted
  mounted="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}' "$id")"
  [[ "$mounted" == "$expected" ]] || fail "candidate db mounts $mounted instead of $expected"
  [[ "$mounted" != "$live_volume" ]] || fail "candidate db must never mount the running volume"
}
require_approval() {
  [[ "${MF_RESET_APPROVAL:-}" == "$1" ]] || fail "set MF_RESET_APPROVAL=$1 to authorize this step"
}

if [[ "$action" == build-candidate ]]; then
  require_approval "build-candidate:${live_db_id:0:12}:$live_volume"
  candidate="minefleet-reset-$(date -u +%Y%m%dt%H%M%Sz)"
  state="$state_root/$candidate"
  [[ ! -e "$state" ]] || fail "state directory already exists"
  mkdir -p -- "$state"; chmod 700 "$state_root" "$state"
  evidence="$state/evidence.log"
  candidate_env "$candidate"
  candidate_volume="${candidate}_db-data"
  docker volume inspect "$candidate_volume" >/dev/null 2>&1 && fail "candidate volume already exists"
  note "BUILD candidate=$candidate volume=$candidate_volume live_db=${live_db_id:0:12} live_volume=$live_volume api_image=${api_image##*@}"
  catalog "$live_db" "$state/live-before.catalog"
  candidate_volume_resolved
  compose_candidate up -d --no-build db >/dev/null 2>&1
  cand_db="$(compose_candidate ps -q db)"
  stop_on_exit+=("$cand_db")
  candidate_db_mount_check "$cand_db" "$candidate_volume"
  wait_healthy "$cand_db"
  note "candidate db healthy on its own network $(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$cand_db")"
  compose_candidate --profile ops run --rm --no-deps migrate >/dev/null 2>"$temporary/migrate.err" \
    || { tail -5 "$temporary/migrate.err" >&2; fail "alembic upgrade head failed on the candidate"; }
  compose_candidate --profile ops run --rm --no-deps migrate python -m app.core.check_schema_revision >/dev/null \
    || fail "candidate schema revision differs from the API image heads"
  note "candidate migrated with the running API image"
  catalog "$cand_db" "$state/candidate-migrated.catalog"
  # Reference rows created by migrations carry fresh UUIDs/timestamps: copy the running rows exactly.
  differing="$(python3 staging_reset.py differing-references --live "$state/live-before.catalog" --candidate "$state/candidate-migrated.catalog")"
  for table in $differing; do
    [[ "$table" =~ ^(saas_plan|role|role_allowed_scope|license_category_ref|vehicle_category_template|vehicle_category_document_template|vehicle_category_template_license)$ ]] \
      || fail "reference table $table differs and cannot be copied (alembic_version/spatial_ref_sys must match)"
    docker exec "$live_db" psql -X -q -U postgres -d minefleet -v ON_ERROR_STOP=1 -c "\\copy public.$table TO STDOUT" > "$temporary/$table.copy"
    docker cp "$temporary/$table.copy" "$cand_db:/tmp/$table.copy" >/dev/null
    printf 'DELETE FROM public.%s;\n\\copy public.%s FROM %s\n' "$table" "$table" "'/tmp/$table.copy'" > "$temporary/$table.sql"
    docker exec -i "$cand_db" psql -X -q -U postgres -d minefleet -v ON_ERROR_STOP=1 -1 < "$temporary/$table.sql" \
      || fail "copy of reference table $table into the candidate failed"
    docker exec "$cand_db" rm -f "/tmp/$table.copy"
    note "reference table $table copied from the running database into the candidate"
  done
  catalog "$cand_db" "$state/candidate-fresh.catalog"
  python3 staging_reset.py compare --live "$state/live-before.catalog" --candidate "$state/candidate-fresh.catalog" \
    --phase fresh --report "$state/compare-fresh.json" | tee -a "$evidence" || fail "candidate comparison failed"
  compose_candidate stop db >/dev/null 2>&1
  printf '{"candidate":"%s","candidate_volume":"%s","live_volume":"%s","live_db":"%s","api_image":"%s"}\n' \
    "$candidate" "$candidate_volume" "$live_volume" "${live_db_id:0:12}" "$api_image" > "$state/state.json"
  note "CANDIDATE OK $candidate (stopped). next: MF_RESET_APPROVAL=bootstrap-candidate:$candidate $0 bootstrap-candidate $candidate"
  exit 0
fi

# --- Steps on an existing candidate ------------------------------------------------------------
state="$state_root/$candidate"
[[ -f "$state/state.json" && ! -L "$state" ]] || { echo "FAIL: unknown candidate $candidate" >&2; exit 2; }
evidence="$state/evidence.log"
state_value() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$state/state.json" "$1"; }
candidate_volume="$(state_value candidate_volume)"
previous_volume="$(state_value live_volume)"
api_image="$(state_value api_image)"
candidate_env "$candidate"

secret_file_ok() {  # secret_file_ok <path> <label>
  [[ "$1" == /* && -f "$1" && ! -L "$1" && "$(stat -c '%a' "$1")" =~ ^[46]00$ ]] \
    || fail "$2 must be an absolute regular file with mode 600 or 400"
}

if [[ "$action" == bootstrap-candidate ]]; then
  require_approval "bootstrap-candidate:$candidate"
  [[ "$live_volume" != "$candidate_volume" ]] || fail "candidate is already the running database"
  : "${MF_RESET_ADMIN_EMAIL:?MF_RESET_ADMIN_EMAIL required}" "${MF_RESET_ADMIN_NAME:?MF_RESET_ADMIN_NAME required}"
  secret_file_ok "${MF_RESET_ADMIN_PASSWORD_FILE:-}" "MF_RESET_ADMIN_PASSWORD_FILE"
  secrets_out="${MF_RESET_ADMIN_SECRETS_OUT:-}"
  [[ "$secrets_out" == /* && ! -e "$secrets_out" ]] || fail "MF_RESET_ADMIN_SECRETS_OUT must be a new absolute path"
  candidate_volume_resolved
  compose_candidate up -d --no-build db >/dev/null 2>&1
  cand_db="$(compose_candidate ps -q db)"
  stop_on_exit+=("$cand_db")
  candidate_db_mount_check "$cand_db" "$candidate_volume"
  wait_healthy "$cand_db"
  admin_password="$(head -n1 "$MF_RESET_ADMIN_PASSWORD_FILE")"
  MF_BOOTSTRAP_PASSWORD="$admin_password" compose_candidate --profile ops run --rm --no-deps -e MF_BOOTSTRAP_PASSWORD \
    migrate minefleet create-platform-admin --email "$MF_RESET_ADMIN_EMAIL" --name "$MF_RESET_ADMIN_NAME" \
    > "$temporary/bootstrap.out" 2>&1 || { tail -3 "$temporary/bootstrap.out" >&2; fail "create-platform-admin failed"; }
  note "$(grep -o 'PLATFORM_ADMIN créé.*' "$temporary/bootstrap.out")"
  second_password="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24) + "Aa1!")')"
  set +e
  MF_BOOTSTRAP_PASSWORD="$second_password" compose_candidate --profile ops run --rm --no-deps -e MF_BOOTSTRAP_PASSWORD \
    migrate minefleet create-platform-admin --email second-admin@example.invalid --name second \
    > "$temporary/bootstrap2.out" 2>&1
  second_status=$?
  set -e
  [[ "$second_status" == 3 ]] || fail "double bootstrap was not refused (exit $second_status)"
  note "double bootstrap refused (exit 3)"
  # Real HTTP checks against a temporary API on the candidate's private network (no port, no edge).
  check_api="$candidate-api-check"
  compose_candidate run -d --rm --no-deps --name "$check_api" api >/dev/null 2>&1
  stop_on_exit=("$check_api" "${stop_on_exit[@]}")
  origin="$(sed -n 's/^MF_ALLOWED_ORIGINS=//p' "$secrets_file" | cut -d, -f1)"
  printf 'MF_CHECK_EMAIL=%s\nMF_CHECK_PASSWORD=%s\nMF_CHECK_ORIGIN=%s\n' "$MF_RESET_ADMIN_EMAIL" "$admin_password" "${origin:-http://localhost}" > "$temporary/check.env"
  for _ in $(seq 60); do
    docker run --rm --network "${candidate}_default" --entrypoint python "$api_image" -c \
      "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://$check_api:8000/api/v1/ready',timeout=3).status==200 else 1)" \
      >/dev/null 2>&1 && break
    sleep 2
  done
  touch "$secrets_out"; chmod 600 "$secrets_out"
  docker run --rm --network "${candidate}_default" --env-file "$temporary/check.env" \
    -v "$deploy_dir/staging-reset-admin-check.py:/check.py:ro" --entrypoint python "$api_image" \
    /check.py enroll "http://$check_api:8000" > "$secrets_out" 2> "$temporary/check.err" \
    || { cat "$temporary/check.err" >&2; rm -f -- "$secrets_out"; fail "platform admin login/MFA checks failed"; }
  sed 's/^/  /' "$temporary/check.err" | tee -a "$evidence"
  docker stop "$check_api" >/dev/null 2>&1 || true
  catalog "$cand_db" "$state/candidate-bootstrapped.catalog"
  python3 staging_reset.py compare --live "$state/live-before.catalog" --candidate "$state/candidate-bootstrapped.catalog" \
    --phase bootstrapped --report "$state/compare-bootstrapped.json" | tee -a "$evidence" || fail "post-bootstrap comparison failed"
  compose_candidate stop db >/dev/null 2>&1
  note "BOOTSTRAP OK $candidate; TOTP secret and recovery codes written to the 600 file (not displayed)"
  note "next (maintenance window): MF_RESET_APPROVAL=cutover:$candidate:${live_db_id:0:12} $0 cutover $candidate"
  exit 0
fi

# --- Cutover / rollback: the only steps touching the running staging -----------------------------
require_live_url() {
  [[ "${MINEFLEET_STAGING_URL:-}" =~ ^https://[a-zA-Z0-9._:-]+/?$ ]] || fail "MINEFLEET_STAGING_URL must be an HTTPS origin"
}
require_quiet_producers() {
  if command -v systemctl >/dev/null 2>&1 && systemctl list-units --no-legend 'minefleet-*.timer' >/dev/null 2>&1; then
    [[ -z "$(systemctl list-units --no-legend --state=active 'minefleet-*.timer')" ]] \
      || fail "stop the minefleet-* timers first (scheduled jobs would write during the switch)"
  else
    [[ "${MF_RESET_NO_SYSTEMD_CONFIRMED:-}" == 1 ]] || fail "cannot verify timers: no systemd (set MF_RESET_NO_SYSTEMD_CONFIRMED=1 only in a lab)"
  fi
  [[ -z "$(docker ps -q --filter label=com.docker.compose.project=$live_project --filter label=com.docker.compose.oneoff=True)" ]] \
    || fail "a one-off minefleet job is running; wait for it to finish"
}
set_db_volume() {  # rewrite only the MF_DB_VOLUME line of .env.prod, atomically, keeping a 600 copy
  local value="$1" stamp
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  cp -p -- "$secrets_file" "$state/env.prod.before-$stamp"
  { grep -v '^MF_DB_VOLUME=' "$secrets_file"; printf 'MF_DB_VOLUME=%s\n' "$value"; } > "$secrets_file.reset-partial"
  chmod 600 "$secrets_file.reset-partial"
  mv -- "$secrets_file.reset-partial" "$secrets_file"
  note ".env.prod: MF_DB_VOLUME=$value (previous file kept in the state directory, mode 600)"
}
switch_db() {  # switch_db <volume>: recreate only the db container on another volume
  local volume="$1" id
  compose_live stop api >/dev/null 2>&1
  set_db_volume "$volume" >&2
  compose_live up -d --no-deps --no-build db >/dev/null 2>&1
  id="$(compose_live ps -q db)"
  wait_healthy "$id"
  [[ "$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}' "$id")" == "$volume" ]] \
    || fail "staging db does not mount $volume after the switch"
  echo "$id"
}
wait_ready() {
  local base="${MINEFLEET_STAGING_URL%/}"
  for _ in $(seq 60); do
    [[ "$(curl -s -o /dev/null -w '%{http_code}' --proto '=https' --max-time 5 "$base/api/v1/ready" || true)" == 200 ]] && return 0
    sleep 2
  done
  return 1
}

if [[ "$action" == cutover ]]; then
  require_approval "cutover:$candidate:${live_db_id:0:12}"
  require_live_url
  [[ "$live_volume" == "$previous_volume" ]] || fail "the running volume changed since the candidate was built"
  [[ -f "$state/candidate-bootstrapped.catalog" ]] || fail "candidate not bootstrapped"
  secret_file_ok "${MF_RESET_ADMIN_PASSWORD_FILE:-}" "MF_RESET_ADMIN_PASSWORD_FILE"
  secret_file_ok "${MF_RESET_ADMIN_SECRETS_OUT:-}" "MF_RESET_ADMIN_SECRETS_OUT (file written by bootstrap)"
  require_quiet_producers
  note "CUTOVER start $candidate: $live_volume -> $candidate_volume"
  MF_BACKUP_SKIP_RETENTION=1 bash backup.sh >/dev/null
  MF_BACKUP_MAX_AGE_HOURS=1 bash probe-backup-freshness.sh | tee -a "$evidence"
  catalog "$live_db" "$state/live-pre-cutover.catalog"
  # The candidate must still be exactly what bootstrap left (nobody wrote to it since).
  candidate_volume_resolved
  compose_candidate up -d --no-build db >/dev/null 2>&1
  cand_db="$(compose_candidate ps -q db)"; stop_on_exit+=("$cand_db"); candidate_db_mount_check "$cand_db" "$candidate_volume"; wait_healthy "$cand_db"
  catalog "$cand_db" "$temporary/candidate-now.catalog"
  python3 staging_reset.py same-state "$state/candidate-bootstrapped.catalog" "$temporary/candidate-now.catalog" >/dev/null \
    || fail "candidate changed since bootstrap"
  compose_candidate stop db >/dev/null 2>&1
  printf '%s\n' "$live_volume" > "$state/previous-volume"
  new_db="$(switch_db "$candidate_volume")"
  rollback_now() {
    echo "FAIL: post-cutover check failed: $1; rolling back to $previous_volume" >&2
    switch_db "$previous_volume" >/dev/null
    compose_live start api >/dev/null 2>&1
    fail "cutover rolled back to $previous_volume after: $1"
  }
  catalog "$new_db" "$state/live-post-cutover.catalog"
  python3 staging_reset.py compare --live "$state/live-before.catalog" --candidate "$state/live-post-cutover.catalog" \
    --phase bootstrapped --report "$state/compare-post-cutover.json" | tee -a "$evidence" || rollback_now "catalog"
  compose_live start api >/dev/null 2>&1
  wait_ready || rollback_now "API not ready"
  MINEFLEET_STAGING_URL="$MINEFLEET_STAGING_URL" bash check-preproduction.sh docker-compose.prod.yml --live >/dev/null || rollback_now "HTTPS probes"
  totp_secret="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["totp_secret"])' "$MF_RESET_ADMIN_SECRETS_OUT")"
  printf 'MF_CHECK_EMAIL=%s\nMF_CHECK_PASSWORD=%s\nMF_CHECK_ORIGIN=%s\nMF_CHECK_TOTP_SECRET=%s\n' \
    "${MF_RESET_ADMIN_EMAIL:?MF_RESET_ADMIN_EMAIL required}" "$(head -n1 "$MF_RESET_ADMIN_PASSWORD_FILE")" \
    "${MINEFLEET_STAGING_URL%/}" "$totp_secret" > "$temporary/login.env"
  set -a; . "$temporary/login.env"; set +a
  python3 staging-reset-admin-check.py login "$MINEFLEET_STAGING_URL" 2>&1 | sed 's/^/  /' | tee -a "$evidence"
  [[ "${PIPESTATUS[0]}" == 0 ]] || rollback_now "admin login"
  note "CUTOVER OK: staging now runs on $candidate_volume; previous volume $previous_volume kept intact"
  note "restart the minefleet-* timers when the new accounts are ready; rollback: MF_RESET_APPROVAL=rollback-cutover:$candidate $0 rollback-cutover $candidate"
  exit 0
fi

# rollback-cutover
require_approval "rollback-cutover:$candidate"
require_live_url
[[ -f "$state/previous-volume" && -f "$state/live-pre-cutover.catalog" ]] || fail "no cutover recorded for $candidate"
previous_volume="$(cat "$state/previous-volume")"
[[ "$live_volume" == "$candidate_volume" ]] || fail "staging is not running on the candidate volume"
docker volume inspect "$previous_volume" >/dev/null 2>&1 || fail "previous volume $previous_volume not found"
require_quiet_producers
note "ROLLBACK start: $candidate_volume -> $previous_volume"
restored_db="$(switch_db "$previous_volume")"
catalog "$restored_db" "$state/live-after-rollback.catalog"
python3 staging_reset.py same-state "$state/live-pre-cutover.catalog" "$state/live-after-rollback.catalog" | tee -a "$evidence" \
  || fail "restored database differs from the pre-cutover state"
compose_live start api >/dev/null 2>&1
wait_ready || fail "API not ready after rollback"
MINEFLEET_STAGING_URL="$MINEFLEET_STAGING_URL" bash check-preproduction.sh docker-compose.prod.yml --live >/dev/null || fail "HTTPS probes after rollback"
note "ROLLBACK OK: staging back on $previous_volume (pre-cutover state proven); candidate volume $candidate_volume kept"
