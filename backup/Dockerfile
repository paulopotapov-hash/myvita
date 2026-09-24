FROM postgres:16-alpine

RUN apk add --no-cache bash coreutils tzdata

COPY scripts/backup_db.sh scripts/restore_db.sh scripts/prune_backups.sh scripts/check_backup.sh \
     scripts/run_scheduled_backup.sh scripts/backup_entrypoint.sh /opt/myvita/
RUN chmod 0555 /opt/myvita/*.sh

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD pgrep crond >/dev/null || exit 1

ENTRYPOINT ["/opt/myvita/backup_entrypoint.sh"]
