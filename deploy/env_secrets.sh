#!/usr/bin/env bash
# Parse a .env into SECRETS / ENVREFS for azure-deploy.sh.
# Trim, strip optional export and quotes, strip CRLF before the empty check
# so DEEPGRAM_API_KEY cannot be silently skipped.

_trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

parse_env_file() {
  local env_file="$1"
  SECRETS=()
  ENVREFS=()
  local line key value secret_name first last
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    line="$(_trim "$line")"
    [[ -z "$line" || "$line" == \#* ]] && continue
    if [[ "$line" == export[[:space:]]* ]]; then
      line="$(_trim "${line#export}")"
    fi
    [[ "$line" == *=* ]] || continue
    key="$(_trim "${line%%=*}")"
    value="${line#*=}"
    value="${value%$'\r'}"
    value="$(_trim "$value")"
    if [[ ${#value} -ge 2 ]]; then
      first="${value:0:1}"
      last="${value: -1}"
      if [[ "$first" == "$last" && ( "$first" == '"' || "$first" == "'" ) ]]; then
        value="${value:1:${#value}-2}"
        value="$(_trim "$value")"
      fi
    fi
    [[ "$key" =~ ^[A-Z][A-Z0-9_]*$ ]] || continue
    [[ -n "$value" ]] || continue
    secret_name="$(printf '%s' "$key" | tr 'A-Z_' 'a-z-')"
    SECRETS+=("${secret_name}=${value}")
    ENVREFS+=("${key}=secretref:${secret_name}")
  done < "$env_file"
}

env_secret_names() {
  local entry
  for entry in "${SECRETS[@]}"; do
    printf '%s\n' "${entry%%=*}"
  done
}

env_has_secret_name() {
  local want="$1" name
  while IFS= read -r name; do
    [[ "$name" == "$want" ]] && return 0
  done < <(env_secret_names)
  return 1
}

require_deepgram_if_production() {
  local environment="$1" env_file="$2"
  if [[ "$environment" == "production" ]] && ! env_has_secret_name "deepgram-api-key"; then
    echo "DEEPGRAM_API_KEY is missing after parsing ${env_file}. A production deploy will 503 Oral board. Fix the line (trim, export, quotes, CRLF) and rerun." >&2
    return 1
  fi
  return 0
}
