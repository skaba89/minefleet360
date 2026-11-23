#!/usr/bin/env bash
# Extract metropolitan France to a self-hosted PMTiles archive, independent from the Guinea map.
# Requires an authenticated/download-capable network, the verified pmtiles CLI, and sufficient free disk space.
# Usage: PATH="$HOME/.local/bin:$PATH" bash scripts/basemap/build-france.sh <out-dir> [YYYYMMDD] [maxzoom]
# Run intentionally by operator: this script is never executed by deploy/migrations/CI.
set -euo pipefail

out_dir=${1:?output directory required}
build=${2:-$(date -u -d "yesterday" +%Y%m%d)}
max_zoom=${3:-14}
bbox="-5.6,41.2,9.9,51.2"

command -v pmtiles >/dev/null || { echo "pmtiles CLI missing" >&2; exit 1; }
[[ "$build" =~ ^[0-9]{8}$ ]] || { echo "invalid build date" >&2; exit 1; }
[[ "$max_zoom" =~ ^(1[0-4]|[0-9])$ ]] || { echo "invalid max zoom (0-14)" >&2; exit 1; }
mkdir -p "$out_dir"
tmp="$out_dir/france.pmtiles.part"
if [[ -e "$tmp" ]]; then
  echo "A previous partial extract exists: $tmp. Remove it manually before retry." >&2
  exit 1
fi
trap 'echo "Extraction interrupted; inspect and remove partial archive if necessary: $tmp" >&2' ERR
pmtiles extract "https://build.protomaps.com/${build}.pmtiles" "$tmp" --bbox="$bbox" --maxzoom="$max_zoom"
pmtiles verify "$tmp"
mv "$tmp" "$out_dir/france.pmtiles"
ls -lh "$out_dir/france.pmtiles"
echo "France PMTiles available; Guinea archive unchanged. Attribution: © OpenStreetMap contributors."
