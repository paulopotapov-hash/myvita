#!/usr/bin/env bash
#
# Restores a myVita database from a dump produced by backup_db.sh.
#
# DESTRUCTIVE: this drops and recreates every object in the target database
# before restoring. Never point this at a database you don't intend to
# fully replace. There is a confirmation prompt for exactly this reason —
# pass --yes only from an already-reviewed, non-interactive DR runbook/script.
#
# Required environment variables:
#   DB_HOST, DB_PORT, DB_NAME, DB_USER, and either PGPASSWORD or PGPASSFILE
#
# Usage:
#   DB_HOST=localhost DB_PORT=5432 DB_NAME=myvita DB_USER=myvita \
#     PGPASSWORD=... ./scripts/restore_db.sh backups/myvita_20260101T000000Z.dump [--yes]
#
set -euo pipefail

dump_file="${1:-}"
confirm_flag="${2:-}"

if [ -z "$dump_file" ]; then
    echo "Usage: $0 <dump_file> [--yes]" >&2
    exit 1
fi
if [ ! -f "$dump_file" ]; then
    echo "ERROR: dump file not found: ${dump_file}" >&2
    exit 1
fi

: "${DB_HOST:?DB_HOST is required}"
: "${DB_PORT:?DB_PORT is required}"
: "${DB_NAME:?DB_NAME is required}"
: "${DB_USER:?DB_USER is required}"
if [ -z "${PGPASSWORD:-}" ] && [ -z "${PGPASSFILE:-}" ]; then
    echo "ERROR: PGPASSWORD or PGPASSFILE is required." >&2
    exit 1
fi

checksum_file="${dump_file}.sha256"
if [ -f "$checksum_file" ]; then
    echo "Verifying backup checksum..."
    if ! (cd "$(dirname "$dump_file")" && sha256sum -c "$(basename "$checksum_file")"); then
        echo "ERROR: backup checksum verification failed; restore was not started." >&2
        exit 1
    fi
fi

if ! pg_restore --list "$dump_file" > /dev/null; then
    echo "ERROR: backup archive is not readable; restore was not started." >&2
    exit 1
fi

if [ "$confirm_flag" != "--yes" ]; then
    echo "This will DROP and REPLACE every object in database '${DB_NAME}' on ${DB_HOST}:${DB_PORT}."
    read -r -p "Type the database name to confirm: " typed_name
    if [ "$typed_name" != "$DB_NAME" ]; then
        echo "Confirmation did not match. Aborting — nothing was touched." >&2
        exit 1
    fi
fi

echo "Restoring ${dump_file} into '${DB_NAME}' on ${DB_HOST}:${DB_PORT}..."

# --clean --if-exists: drop existing objects first, without failing on
# objects that don't exist yet (e.g. restoring into a freshly-created,
# still-empty database). -1: wrap the whole restore in a single
# transaction — a failure partway through rolls back completely instead
# of leaving the database in a half-restored state.
if pg_restore \
    -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    --clean --if-exists -1 \
    "$dump_file"; then
    echo "Restore completed."
else
    echo "ERROR: pg_restore failed. The transaction was rolled back (-1), so '${DB_NAME}' should be unchanged from before this run — but verify before relying on that." >&2
    exit 1
fi

echo "Next steps: run 'alembic upgrade head' against this database if the dump predates the current migration state, then verify the app's /ready endpoint."
