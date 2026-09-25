#!/usr/bin/env bash
set -euo pipefail

backup_dir="${1:-/backups}"
retention_days="${BACKUP_RETENTION_DAYS:-14}"

if ! [[ "$retention_days" =~ ^[0-9]+$ ]] || [ "$retention_days" -lt 1 ]; then
    echo "ERROR: BACKUP_RETENTION_DAYS must be a positive integer." >&2
    exit 1
fi
if [ ! -d "$backup_dir" ]; then
    echo "ERROR: backup directory does not exist: $backup_dir" >&2
    exit 1
fi

removed=0
while IFS= read -r -d '' dump_file; do
    checksum_file="${dump_file}.sha256"
    rm -f "$dump_file"
    [ ! -f "$checksum_file" ] || rm -f "$checksum_file"
    removed=$((removed + 1))
done < <(find "$backup_dir" -maxdepth 1 -type f -name 'myvita_*.dump' -mtime "+${retention_days}" -print0)

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Retention completed: removed=${removed} retention_days=${retention_days}"
