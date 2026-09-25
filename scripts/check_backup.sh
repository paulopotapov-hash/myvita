#!/usr/bin/env bash
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

latest=""
latest_mtime=0
while IFS= read -r -d '' candidate; do
    candidate_mtime="$(mtime "$candidate")"
    if [ "$candidate_mtime" -gt "$latest_mtime" ]; then
        latest="$candidate"
        latest_mtime="$candidate_mtime"
    fi
done < <(find "$backup_dir" -maxdepth 1 -type f -name 'myvita_*.dump' -print0 2>/dev/null)
if [ -z "$latest" ] || [ ! -s "$latest" ]; then
    echo "ERROR: no non-empty completed backup found in $backup_dir" >&2
    exit 1
fi

now="$(date +%s)"
modified="$(mtime "$latest")"
age_seconds="$((now - modified))"
if [ "$age_seconds" -gt "$((max_age_hours * 3600))" ]; then
    echo "ERROR: latest backup is too old: $(basename "$latest") age_seconds=$age_seconds" >&2
    exit 1
fi

checksum_file="${latest}.sha256"
if [ ! -s "$checksum_file" ] || ! (cd "$backup_dir" && sha256sum -c "$(basename "$checksum_file")" > /dev/null); then
    echo "ERROR: checksum missing or invalid for $(basename "$latest")" >&2
    exit 1
fi
if ! pg_restore --list "$latest" > /dev/null; then
    echo "ERROR: archive validation failed for $(basename "$latest")" >&2
    exit 1
fi

echo "Backup check OK: file=$(basename "$latest") age_seconds=$age_seconds"
