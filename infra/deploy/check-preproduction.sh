#!/usr/bin/env bash
# Read-only checks for a MineFleet staging deployment.
set -euo pipefail

COMPOSE_FILE="${1:-infra/deploy/docker-compose.prod.yml}"
if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "FAIL: missing compose file: $COMPOSE_FILE" >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "FAIL: docker command is required" >&2
  exit 1
fi
echo "Checking Compose syntax (no containers started)..."
# Use fake non-empty placeholders for mandatory variables; never print or load real secrets.
POSTGRES_PASSWORD=check MF_OWNER_PASSWORD=check MF_APP_PASSWORD=check \
MF_JWT_SECRET=check MF_MFA_ENCRYPTION_KEY=check MF_ENV=staging \
MF_DOMAIN=staging.example.invalid MF_ACME_EMAIL=ops@example.invalid \
  docker compose -f "$COMPOSE_FILE" config --quiet
echo "OK: Compose configuration parsed."

if [[ "${2:-}" == "--live" ]]; then
  BASE_URL="${MINEFLEET_STAGING_URL:-}"
  if [[ ! "$BASE_URL" =~ ^https://[a-zA-Z0-9._:-]+/?$ ]]; then
    echo "FAIL: MINEFLEET_STAGING_URL must be an HTTPS origin without paths, query or credentials" >&2
    exit 1
  fi
  if ! command -v curl >/dev/null 2>&1; then
    echo "FAIL: curl command is required" >&2
    exit 1
  fi
  BASE_URL="${BASE_URL%/}"
  # No redirect, insecure TLS, credentials or response bodies.
  for route in / /api/v1/health /api/v1/ready; do
    if ! code="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \\
      --connect-timeout 5 --max-time 12 --proto '=https' "$BASE_URL$route")"; then
      echo "FAIL: staging HTTPS probe unreachable: $route" >&2
      exit 1
    fi
    if [[ "$code" != "200" ]]; then
      echo "FAIL: staging probe $route returned HTTP $code" >&2
      exit 1
    fi
    echo "OK: staging $route returned HTTP 200"
  done
fi
echo "NOTICE: this is a smoke gate, not proof of backups, monitoring, restore or security."
