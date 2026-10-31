#!/usr/bin/env bash
# Restricted DB readiness probe through the HTTPS API, no Docker socket or DB credentials.
set -euo pipefail
url="${MINEFLEET_BASE_URL:-}"
if [[ ! "$url" =~ ^https://[a-zA-Z0-9._:-]+/?$ ]]; then
  echo "UNKNOWN: set MINEFLEET_BASE_URL to a valid HTTPS origin" >&2
  exit 3
fi
command -v curl >/dev/null || { echo "UNKNOWN: curl missing" >&2; exit 3; }
url="${url%/}"
if ! status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  --proto '=https' --connect-timeout 5 --max-time 12 "$url/api/v1/ready")"; then
  echo "CRITICAL: database readiness endpoint unavailable" >&2
  exit 2
fi
if [[ "$status" != "200" ]]; then
  echo "CRITICAL: database readiness returned HTTP $status" >&2
  exit 2
fi
echo "OK: database readiness checked through restricted API role"
