#!/usr/bin/env bash
# Produit le fond de carte auto-hébergé : extrait OpenStreetMap de la Guinée au format PMTiles (docs/GPS_LIVE_MAP.md).
#
# Prérequis (à installer par l'exploitant, après vérification de la somme de contrôle de la version publiée) :
#   - l'outil `pmtiles` (https://github.com/protomaps/go-pmtiles/releases) dans le PATH.
# Usage : scripts/basemap/build-guinee.sh <dossier de sortie> [AAAAMMJJ du build Protomaps] [zoom max]
# Le fichier est lu par plages depuis le build quotidien de Protomaps (données OSM, licence ODbL) : seule la zone
# de la Guinée est téléchargée. Déposer ensuite le fichier dans MF_BASEMAP_DIR (monté en lecture seule dans le
# conteneur web) ; aucun redémarrage n'est nécessaire.
set -euo pipefail

out_dir=${1:?dossier de sortie requis}
build=${2:-$(date -u -d "yesterday" +%Y%m%d)}
max_zoom=${3:-14}
# Guinée avec une marge de quelques kilomètres : ouest, sud, est, nord (WGS 84).
bbox="-15.2,7.1,-7.5,12.8"

command -v pmtiles >/dev/null || { echo "outil pmtiles introuvable (voir l'en-tête du script)" >&2; exit 1; }
mkdir -p "$out_dir"
tmp="$out_dir/guinee.pmtiles.part"
pmtiles extract "https://build.protomaps.com/${build}.pmtiles" "$tmp" --bbox="$bbox" --maxzoom="$max_zoom"
pmtiles verify "$tmp"
mv "$tmp" "$out_dir/guinee.pmtiles"
ls -lh "$out_dir/guinee.pmtiles"
echo "Fond de carte prêt (build ${build}, zoom max ${max_zoom}). Attribution : © contributeurs OpenStreetMap."
