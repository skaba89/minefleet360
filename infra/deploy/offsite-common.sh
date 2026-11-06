#!/usr/bin/env bash
# Shared validation for off-site backup scripts. This repository file is trusted;
# offsite.env is parsed as data by Python and is never sourced as shell code.

offsite_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
offsite_config_file="${MF_OFFSITE_CONFIG_FILE:-$offsite_script_dir/offsite.env}"

offsite_fail() {
  echo "FAIL: $*" >&2
  return 1
}

offsite_restricted_file() {
  local path="$1"
  local label="$2"
  local mode
  if [[ ! -f "$path" || -L "$path" ]]; then
    offsite_fail "$label must be a regular non-symlink file"
    return 1
  fi
  mode="$(stat -c '%a' -- "$path")"
  if [[ "$mode" != "400" && "$mode" != "600" ]]; then
    offsite_fail "$label permissions must be 400 or 600 (observed $mode)"
    return 1
  fi
}

load_offsite_config() {
  local parsed line key value
  if [[ "$offsite_config_file" != /* ]]; then
    offsite_fail "MF_OFFSITE_CONFIG_FILE must be absolute"
    return 1
  fi
  offsite_restricted_file "$offsite_config_file" "off-site configuration" || return 1
  parsed="$(python3 "$offsite_script_dir/offsite_config.py" emit-env "$offsite_config_file")" || return 1

  MF_OFFSITE_REMOTE=""
  MF_OFFSITE_PASSPHRASE_FILE=""
  MF_OFFSITE_RETENTION_DAYS=""
  while IFS= read -r line; do
    key="${line%%=*}"
    value="${line#*=}"
    case "$key" in
      MF_OFFSITE_REMOTE) MF_OFFSITE_REMOTE="$value" ;;
      MF_OFFSITE_PASSPHRASE_FILE) MF_OFFSITE_PASSPHRASE_FILE="$value" ;;
      MF_OFFSITE_RETENTION_DAYS) MF_OFFSITE_RETENTION_DAYS="$value" ;;
      *) offsite_fail "unexpected key returned by parser"; return 1 ;;
    esac
  done <<< "$parsed"

  offsite_restricted_file "$MF_OFFSITE_PASSPHRASE_FILE" "off-site passphrase" || return 1
  local passphrase_size
  passphrase_size="$(wc -c < "$MF_OFFSITE_PASSPHRASE_FILE")"
  if [[ ! "$passphrase_size" =~ ^[0-9]+$ || "$passphrase_size" -lt 32 || "$passphrase_size" -gt 4096 ]]; then
    offsite_fail "off-site passphrase must contain between 32 and 4096 bytes"
    return 1
  fi
  command -v gpg >/dev/null || { offsite_fail "gpg is required"; return 1; }
  command -v rclone >/dev/null || { offsite_fail "rclone is required"; return 1; }
}
