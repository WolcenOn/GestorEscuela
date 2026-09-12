#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required" >&2
  exit 2
fi

backup="${1:-}"
if [[ -z "$backup" || ! -f "$backup" ]]; then
  echo "Usage: DATABASE_URL=... $0 <backup.dump>" >&2
  exit 2
fi

pg_url="${DATABASE_URL/postgresql+psycopg:\/\//postgresql:\/\/}"
pg_url="${pg_url/postgres:\/\//postgresql:\/\/}"

pg_restore --list "$backup" >/dev/null
pg_restore \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  --exit-on-error \
  --dbname="$pg_url" \
  "$backup"
