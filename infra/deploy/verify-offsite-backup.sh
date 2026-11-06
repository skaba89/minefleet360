#!/usr/bin/env bash
# Download, authenticate, decrypt and restore one exact off-site backup object.
set -euo pipefail
umask 077

script_dir="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=offsite-common.sh
. "$script_dir/offsite-common.sh"

if [[ $# -ne 1 && $# -ne 3 ]]; then
  echo "Usage: $0 minefleet-YYYYMMDDTHHMMSSZ.dump.gpg [--api-image IMAGE]" >&2
  exit 2
fi
object="$1"
if [[ ! "$object" =~ ^minefleet-[0-9]{8}T[0-9]{6}Z\.dump\.gpg$ ]]; then
  echo "FAIL: object must be one canonical MineFleet encrypted backup basename" >&2
  exit 2
fi
restore_args=()
if [[ $# -eq 3 ]]; then
  if [[ "$2" != "--api-image" || -z "$3" || ! "$3" =~ ^[A-Za-z0-9][A-Za-z0-9._/:@-]+$ ]]; then
    echo "FAIL: expected --api-image followed by a Docker image reference" >&2
    exit 2
  fi
  restore_args=(--api-image "$3")
fi

load_offsite_config
temporary_parent="${MF_OFFSITE_RESTORE_TMPDIR:-${RUNNER_TEMP:-/tmp}}"
if [[ "$temporary_parent" != /* || ! -d "$temporary_parent" || -L "$temporary_parent" ]]; then
  echo "FAIL: restore temporary parent must be an absolute non-symlink directory" >&2
  exit 2
fi
work_dir="$(mktemp -d --tmpdir="$temporary_parent" minefleet-offsite-restore.XXXXXX)"
encrypted="$work_dir/$object"
checksum="$encrypted.sha256"
archive="$work_dir/${object%.gpg}"
started_epoch="$(date -u +%s)"
cleanup() { rm -rf -- "$work_dir"; }
trap cleanup EXIT

rclone copyto --quiet "$MF_OFFSITE_REMOTE/$object" "$encrypted" </dev/null
rclone copyto --quiet "$MF_OFFSITE_REMOTE/$object.sha256" "$checksum" </dev/null

checksum_size="$(wc -c < "$checksum")"
checksum_lines="$(wc -l < "$checksum")"
expected_digest=""
expected_name=""
extra=""
read -r expected_digest expected_name extra < "$checksum" || true
if [[ ! "$checksum_size" =~ ^[0-9]+$ || "$checksum_size" -gt 256 \
  || "$checksum_lines" != "1" || -n "$extra" || "$expected_name" != "$object" \
  || ! "$expected_digest" =~ ^[0-9a-f]{64}$ ]]; then
  echo "FAIL: remote checksum sidecar is malformed" >&2
  exit 1
fi
observed_digest="$(sha256sum -- "$encrypted" | cut -d' ' -f1)"
if [[ "$observed_digest" != "$expected_digest" ]]; then
  echo "FAIL: encrypted backup checksum mismatch" >&2
  exit 1
fi

gpg --batch --yes --quiet --no-symkey-cache --pinentry-mode loopback \
  --passphrase-file "$MF_OFFSITE_PASSPHRASE_FILE" --output "$archive" --decrypt "$encrypted"
chmod 600 "$archive"
bash "$script_dir/verify-restore.sh" "$archive" "${restore_args[@]}"

finished_epoch="$(date -u +%s)"
backup_utc="${object#minefleet-}"
backup_utc="${backup_utc%.dump.gpg}"
echo "OFFSITE_RESTORE_OK object=$object backup_utc=$backup_utc duration_seconds=$((finished_epoch - started_epoch))"
echo "NOTICE: measured duration is evidence for this exercise only, not a contractual RPO/RTO certification."
