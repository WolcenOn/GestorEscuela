#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required" >&2
  exit 2
fi

output="${1:-${BACKUP_FILE:-gestor-escuela-$(date -u +%Y%m%dT%H%M%SZ).dump}}"
pg_url="${DATABASE_URL/postgresql+psycopg:\/\//postgresql:\/\/}"
pg_url="${pg_url/postgres:\/\//postgresql:\/\/}"

umask 077
mkdir -p "$(dirname "$output")"
pg_dump \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file="$output" \
  "$pg_url"

pg_restore --list "$output" >/dev/null
printf '%s\n' "$output"
