#!/usr/bin/env bash
#
# Backs up the myVita PostgreSQL database with pg_dump, in the custom
# ("-Fc") format, which is what restore_db.sh expects — it's compressed
# and supports pg_restore's selective/parallel restore, unlike a plain
# SQL dump.
#
# A Docker volume (myvita_pg_data) is NOT a backup: it protects against
# a container being removed, not against a bad migration, a bad DELETE,
# disk corruption, or the whole host disappearing. This script is the
# actual backup.
#
# Required environment variables (no defaults — this script refuses to
# guess a database to dump):
#   DB_HOST, DB_PORT, DB_NAME, DB_USER, PGPASSWORD
# (PGPASSWORD is pg_dump's own standard variable name — libpq reads it
# directly, so we don't have to pass the password on the command line
# where it would show up in `ps` output or shell history.)
#
# Usage:
#   DB_HOST=localhost DB_PORT=5432 DB_NAME=myvita DB_USER=myvita \
#     PGPASSWORD=... ./scripts/backup_db.sh [output_dir]
#
set -euo pipefail

output_dir="${1:-./backups}"

: "${DB_HOST:?DB_HOST is required}"
: "${DB_PORT:?DB_PORT is required}"
: "${DB_NAME:?DB_NAME is required}"
: "${DB_USER:?DB_USER is required}"
: "${PGPASSWORD:?PGPASSWORD is required (never pass the password as an argument)}"

mkdir -p "$output_dir"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
dump_file="${output_dir}/myvita_${timestamp}.dump"

echo "Backing up '${DB_NAME}' from ${DB_HOST}:${DB_PORT} -> ${dump_file}"

# -Fc: custom format (compressed, restorable with pg_restore, supports -j
# for parallel restore on a large database later).
if pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -Fc -f "$dump_file"; then
    size="$(du -h "$dump_file" | cut -f1)"
    echo "Backup completed: ${dump_file} (${size})"
else
    echo "ERROR: pg_dump failed — no valid backup was produced." >&2
    rm -f "$dump_file"
    exit 1
fi

# Verification (see section 9 of the hardening spec: "quando possível,
# verificar que o backup pode realmente ser restaurado"). pg_restore --list
# reads the archive's table of contents without touching any database —
# a corrupt/truncated dump file fails this immediately, catching the most
# common failure mode (disk full mid-dump, killed process) right here
# instead of at restore time, when it's too late.
echo "Verifying archive integrity (pg_restore --list)..."
if pg_restore --list "$dump_file" > /dev/null; then
    echo "Verification OK: archive is readable."
else
    echo "ERROR: backup file failed integrity verification." >&2
    exit 1
fi
