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
#   DB_HOST, DB_PORT, DB_NAME, DB_USER, and either PGPASSWORD or PGPASSFILE.
# Both credential mechanisms are native to libpq, so the password never has
# to be passed as a command-line argument where it would show up in `ps`.
#
# Usage:
#   DB_HOST=localhost DB_PORT=5432 DB_NAME=myvita DB_USER=myvita \
#     PGPASSWORD=... ./scripts/backup_db.sh [output_dir]
#
set -euo pipefail
umask 077

output_dir="${1:-./backups}"

: "${DB_HOST:?DB_HOST is required}"
: "${DB_PORT:?DB_PORT is required}"
: "${DB_NAME:?DB_NAME is required}"
: "${DB_USER:?DB_USER is required}"
if [ -z "${PGPASSWORD:-}" ] && [ -z "${PGPASSFILE:-}" ]; then
    echo "ERROR: PGPASSWORD or PGPASSFILE is required." >&2
    exit 1
fi

mkdir -p "$output_dir"
chmod 700 "$output_dir"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
dump_file="${output_dir}/myvita_${timestamp}.dump"
tmp_file="$(mktemp "${output_dir}/.myvita_${timestamp}.dump.tmp.XXXXXX")"
checksum_file="${dump_file}.sha256"
tmp_checksum="${checksum_file}.tmp"
started_at="$(date +%s)"

cleanup() {
    rm -f "$tmp_file" "$tmp_checksum"
}
trap cleanup EXIT INT TERM

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Backup started: database=${DB_NAME} file=$(basename "$dump_file")"

# -Fc: custom format (compressed, restorable with pg_restore, supports -j
# for parallel restore on a large database later).
if ! pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -Fc -f "$tmp_file"; then
    echo "ERROR: pg_dump failed — no valid backup was produced." >&2
    exit 1
fi

if [ ! -s "$tmp_file" ]; then
    echo "ERROR: pg_dump produced an empty backup." >&2
    exit 1
fi

# Verification (see section 9 of the hardening spec: "quando possível,
# verificar que o backup pode realmente ser restaurado"). pg_restore --list
# reads the archive's table of contents without touching any database —
# a corrupt/truncated dump file fails this immediately, catching the most
# common failure mode (disk full mid-dump, killed process) right here
# instead of at restore time, when it's too late.
echo "Verifying archive integrity (pg_restore --list)..."
if pg_restore --list "$tmp_file" > /dev/null; then
    echo "Verification OK: archive is readable."
else
    echo "ERROR: backup file failed integrity verification." >&2
    exit 1
fi

# Calculate the digest while the archive still has its temporary name, but
# record the final basename expected by `sha256sum -c`. Publishing the
# checksum first is safe (checks ignore orphan checksums); publishing the dump
# last means a completed .dump is never visible without its checksum.
if ! digest="$(sha256sum "$tmp_file" | awk '{print $1}')" || [ -z "$digest" ]; then
    echo "ERROR: checksum generation failed; removing the unverified new backup." >&2
    exit 1
fi
printf '%s  %s\n' "$digest" "$(basename "$dump_file")" > "$tmp_checksum"
mv "$tmp_checksum" "$checksum_file"

# Rename on the same filesystem is atomic: retention/check scripts never see
# a partially-written final .dump file.
if ! mv "$tmp_file" "$dump_file"; then
    rm -f "$checksum_file"
    echo "ERROR: could not publish the completed backup." >&2
    exit 1
fi

size="$(du -h "$dump_file" | cut -f1)"
duration="$(( $(date +%s) - started_at ))"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Backup completed successfully: file=$(basename "$dump_file") size=${size} duration_seconds=${duration}"
