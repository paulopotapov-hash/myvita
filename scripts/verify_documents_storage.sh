#!/usr/bin/env bash
#
# Read-only consistency check between the `documents` table and document
# storage. NEVER deletes or modifies anything.
#
#   missing_files  document rows whose storage_key has no file (downloads would 404)
#   orphan_files   stored objects with no document row
#   pending_deletes `.pending-*` files left by an interrupted delete
#   unexpected     any other entry in the storage directory
#
# Only storage keys and document ids are printed — never filenames or content.
#
# Required environment: DB_HOST, DB_PORT, DB_NAME, DB_USER and PGPASSWORD or PGPASSFILE.
#
# Usage: ./scripts/verify_documents_storage.sh <storage_dir> [--allow-orphans]
#
#   --allow-orphans  report orphan files but do not fail on them. Expected right
#                    after a restore: uploads that happened between the database
#                    dump and the documents archive leave files without rows.
#
# Exit codes: 0 consistent, 1 discrepancies found, 2 usage/connection error.
#
set -euo pipefail

storage_dir=""
allow_orphans=false
for arg in "$@"; do
    case "$arg" in
        --allow-orphans) allow_orphans=true ;;
        -*) echo "ERROR: unknown option: $arg" >&2; exit 2 ;;
        *) storage_dir="$arg" ;;
    esac
done
[ -n "$storage_dir" ] || { echo "Usage: $0 <storage_dir> [--allow-orphans]" >&2; exit 2; }
[ -d "$storage_dir" ] || { echo "ERROR: storage directory does not exist: $storage_dir" >&2; exit 2; }
: "${DB_HOST:?DB_HOST is required}" "${DB_PORT:?DB_PORT is required}" "${DB_NAME:?DB_NAME is required}" "${DB_USER:?DB_USER is required}"
if [ -z "${PGPASSWORD:-}" ] && [ -z "${PGPASSFILE:-}" ]; then
    echo "ERROR: PGPASSWORD or PGPASSFILE is required." >&2; exit 2
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT INT TERM

if ! psql -X -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -At \
        -c "select storage_key from documents order by 1" > "${work}/db_keys"; then
    echo "ERROR: could not read document records from the database." >&2
    exit 2
fi

: > "${work}/stored_keys"; : > "${work}/pending"; : > "${work}/unexpected"
for path in "$storage_dir"/* "$storage_dir"/.[!.]*; do
    [ -e "$path" ] || continue
    name="$(basename "$path")"
    if [ -f "$path" ] && [[ "$name" =~ ^[0-9a-f]{32}$ ]]; then
        echo "$name" >> "${work}/stored_keys"
    elif [[ "$name" == .pending-* ]]; then
        echo "$name" >> "${work}/pending"
    else
        echo "$name" >> "${work}/unexpected"
    fi
done
LC_ALL=C sort -o "${work}/db_keys" "${work}/db_keys"
LC_ALL=C sort -o "${work}/stored_keys" "${work}/stored_keys"

LC_ALL=C comm -23 "${work}/db_keys" "${work}/stored_keys" > "${work}/missing"
LC_ALL=C comm -13 "${work}/db_keys" "${work}/stored_keys" > "${work}/orphans"
count() { wc -l < "$1" | tr -d ' '; }
missing="$(count "${work}/missing")"
orphans="$(count "${work}/orphans")"
pending="$(count "${work}/pending")"
unexpected="$(count "${work}/unexpected")"

while IFS= read -r key; do echo "missing_file storage_key=${key}"; done < "${work}/missing"
while IFS= read -r key; do echo "orphan_file storage_key=${key}"; done < "${work}/orphans"
while IFS= read -r name; do echo "pending_delete entry=${name}"; done < "${work}/pending"
[ "$unexpected" = "0" ] || echo "unexpected_entries=${unexpected} (non-document names in storage; not listed)"

echo "DOCUMENTS_CONSISTENCY records=$(count "${work}/db_keys") stored_files=$(count "${work}/stored_keys") missing_files=${missing} orphan_files=${orphans} pending_deletes=${pending} unexpected_entries=${unexpected}"

if [ "$missing" != "0" ] || [ "$unexpected" != "0" ] || { [ "$orphans" != "0" ] && [ "$allow_orphans" != "true" ]; }; then
    exit 1
fi
