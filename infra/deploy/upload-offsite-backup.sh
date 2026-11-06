#!/usr/bin/env bash
# Encrypt one canonical MineFleet dump and upload only its ciphertext and checksum.
set -euo pipefail
umask 077

script_dir="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=offsite-common.sh
. "$script_dir/offsite-common.sh"

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /absolute/path/minefleet-YYYYMMDDTHHMMSSZ.dump" >&2
  exit 2
fi
archive="$1"
if [[ "$archive" != /* || ! -f "$archive" || -L "$archive" || ! -s "$archive" ]]; then
  echo "FAIL: backup archive must be an absolute, non-empty, regular non-symlink file" >&2
  exit 2
fi
archive_name="$(basename -- "$archive")"
if [[ ! "$archive_name" =~ ^minefleet-[0-9]{8}T[0-9]{6}Z\.dump$ ]]; then
  echo "FAIL: backup archive name must use minefleet-YYYYMMDDTHHMMSSZ.dump" >&2
  exit 2
fi

load_offsite_config
work_dir="$(mktemp -d --tmpdir="$(dirname -- "$archive")" .minefleet-offsite-upload.XXXXXX)"
encrypted_name="$archive_name.gpg"
encrypted="$work_dir/$encrypted_name"
checksum="$work_dir/$encrypted_name.sha256"
remote_object="$MF_OFFSITE_REMOTE/$encrypted_name"
remote_checksum="$remote_object.sha256"

cleanup() {
  rm -rf -- "$work_dir"
}
trap cleanup EXIT

gpg --batch --yes --quiet --no-symkey-cache --pinentry-mode loopback \
  --symmetric --cipher-algo AES256 --s2k-digest-algo SHA512 --compress-algo none \
  --passphrase-file "$MF_OFFSITE_PASSPHRASE_FILE" --output "$encrypted" "$archive"
digest="$(sha256sum -- "$encrypted" | cut -d' ' -f1)"
printf '%s  %s\n' "$digest" "$encrypted_name" > "$checksum"

rclone copyto --quiet --immutable "$encrypted" "$remote_object" </dev/null
rclone copyto --quiet --immutable "$checksum" "$remote_checksum" </dev/null

# Retention is confined to the MineFleet namespace. Unrelated remote objects are excluded.
rclone delete --quiet --min-age "${MF_OFFSITE_RETENTION_DAYS}d" \
  --filter '+ minefleet-????????T??????Z.dump.gpg' \
  --filter '+ minefleet-????????T??????Z.dump.gpg.sha256' \
  --filter '- **' "$MF_OFFSITE_REMOTE" </dev/null

echo "OFFSITE_UPLOAD_OK object=$encrypted_name sha256=$digest retention_days=$MF_OFFSITE_RETENTION_DAYS"
