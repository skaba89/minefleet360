#!/usr/bin/env bash
# Read-only HTTPS probe for MineFleet 360. Safe for cron and external monitoring.
set -euo pipefail

url="${MINEFLEET_BASE_URL:-}"
if [[ $# -eq 2 && "$1" == "--url" ]]; then url="$2"; elif [[ $# -ne 0 ]]; then
  echo "Usage: MINEFLEET_BASE_URL=https://example.org $0 [--url https://example.org]" >&2
  exit 2
fi
if [[ ! "$url" =~ ^https://[a-zA-Z0-9._:-]+(/)?$ ]]; then
  echo "CRITICAL: supply an HTTPS origin without credentials, query or path" >&2
  exit 2
fi
command -v curl >/dev/null || { echo "UNKNOWN: curl missing" >&2; exit 3; }
url="${url%/}"
# Keep the response body out of logs; require a 2xx HTTP status and no redirect.
start="$(date +%s)"
if ! code="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  --max-time 12 --connect-timeout 5 --proto '=https' \
  "$url/api/v1/health")"; then
  echo "CRITICAL: health endpoint unreachable" >&2
  exit 2
fi
if [[ "$code" != "200" ]]; then
  echo "CRITICAL: unexpected HTTP status $code" >&2
  exit 2
fi
duration="$(( $(date +%s) - start ))"
echo "OK: MineFleet HTTP health responded 200 in ${duration}s"
