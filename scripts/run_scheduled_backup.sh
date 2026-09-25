#!/usr/bin/env bash
set -euo pipefail

if ! /opt/myvita/backup_db.sh /backups; then
    /opt/myvita/write_backup_metrics.sh local-failure
    exit 1
fi
/opt/myvita/write_backup_metrics.sh local-success

if [ "${OFFSITE_BACKUP_ENABLED:-false}" = "true" ]; then
    latest="$(find /backups -maxdepth 1 -type f -name 'myvita_*.dump' | sort | tail -n 1)"
    if ! /opt/myvita/upload_offsite_backup.sh "$latest"; then
        /opt/myvita/write_backup_metrics.sh offsite-failure
        exit 1
    fi
    /opt/myvita/write_backup_metrics.sh offsite-success
    /opt/myvita/prune_offsite_backups.sh
fi

/opt/myvita/prune_backups.sh /backups
