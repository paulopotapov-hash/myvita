#!/usr/bin/env bash
#
# Stale/invalid backup detection for monitoring and operators.
#
# Checks the newest PostgreSQL dump and, when DOCUMENTS_BACKUP_ENABLED=true,
# the newest documents archive: it must exist, be younger than
# BACKUP_MAX_AGE_HOURS (default 36), match its .sha256 and be a readable
# archive. Prints one human line per backup and a final machine-readable line:
#
#   BACKUP_STATUS postgres=OK|STALE|MISSING|INVALID documents=OK|...|DISABLED
#
# Exit code 0 only when every checked backup is OK.
#
# Usage: check_backup.sh [backup_dir]
#
set -euo pipefail

backup_dir="${1:-/backups}"
max_age_hours="${BACKUP_MAX_AGE_HOURS:-36}"

mtime() {
    stat -c %Y "$1" 2>/dev/null || stat -f %m "$1"
}

if ! [[ "$max_age_hours" =~ ^[0-9]+$ ]] || [ "$max_age_hours" -lt 1 ]; then
    echo "ERROR: BACKUP_MAX_AGE_HOURS must be a positive integer." >&2
    exit 1
fi

# check_latest <label> <find-pattern> <archive-validator-fn>; sets result_<label>.
check_latest() {
    local label="$1" pattern="$2" validator="$3" latest="" latest_mtime=0 candidate candidate_mtime
    while IFS= read -r -d '' candidate; do
        candidate_mtime="$(mtime "$candidate")"
        if [ "$candidate_mtime" -gt "$latest_mtime" ]; then
            latest="$candidate"
            latest_mtime="$candidate_mtime"
        fi
    done < <(find "$backup_dir" -maxdepth 1 -type f -name "$pattern" -print0 2>/dev/null)
    if [ -z "$latest" ] || [ ! -s "$latest" ]; then
        echo "ERROR: no non-empty completed ${label} backup found in $backup_dir" >&2
        printf -v "result_${label}" MISSING; return 1
    fi

    local age_seconds="$(( $(date +%s) - $(mtime "$latest") ))"
    if [ "$age_seconds" -gt "$((max_age_hours * 3600))" ]; then
        echo "ERROR: latest ${label} backup is too old: $(basename "$latest") age_seconds=$age_seconds" >&2
        printf -v "result_${label}" STALE; return 1
    fi

    local checksum_file="${latest}.sha256"
    if [ ! -s "$checksum_file" ] || ! (cd "$backup_dir" && sha256sum -c "$(basename "$checksum_file")" > /dev/null); then
        echo "ERROR: checksum missing or invalid for $(basename "$latest")" >&2
        printf -v "result_${label}" INVALID; return 1
    fi
    if ! "$validator" "$latest"; then
        echo "ERROR: archive validation failed for $(basename "$latest")" >&2
        printf -v "result_${label}" INVALID; return 1
    fi

    echo "Backup check OK: file=$(basename "$latest") age_seconds=$age_seconds"
    printf -v "result_${label}" OK
}
validate_dump() { pg_restore --list "$1" > /dev/null; }
validate_documents() { gzip -t "$1" && tar -tzf "$1" > /dev/null; }

status=0
result_postgres=""
result_documents=DISABLED
check_latest postgres 'myvita_[0-9]*.dump' validate_dump || status=1
if [ "${DOCUMENTS_BACKUP_ENABLED:-false}" = "true" ]; then
    check_latest documents 'myvita_documents_[0-9]*.tar.gz' validate_documents || status=1
fi
echo "BACKUP_STATUS postgres=${result_postgres} documents=${result_documents}"
exit "$status"
