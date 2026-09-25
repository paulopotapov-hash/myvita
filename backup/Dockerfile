FROM postgres:16-alpine

RUN apk add --no-cache aws-cli bash coreutils tzdata

COPY scripts/backup_db.sh scripts/restore_db.sh scripts/prune_backups.sh scripts/check_backup.sh \
     scripts/upload_offsite_backup.sh scripts/download_offsite_backup.sh \
     scripts/prune_offsite_backups.sh scripts/write_backup_metrics.sh \
     scripts/run_scheduled_backup.sh scripts/backup_entrypoint.sh /opt/myvita/
RUN chmod 0555 /opt/myvita/*.sh

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD pgrep crond >/dev/null || exit 1

ENTRYPOINT ["/opt/myvita/backup_entrypoint.sh"]
