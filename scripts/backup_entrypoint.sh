#!/usr/bin/env bash
set -euo pipefail

: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${BACKUP_SCHEDULE:=0 3 * * *}"
: "${TZ:=UTC}"

if [[ "$BACKUP_SCHEDULE" == *$'\n'* ]] || [[ "$BACKUP_SCHEDULE" == *$'\r'* ]] || [ "$(awk '{print NF}' <<< "$BACKUP_SCHEDULE")" -ne 5 ]; then
    echo "ERROR: BACKUP_SCHEDULE must contain exactly five cron fields." >&2
    exit 1
fi

umask 077
mkdir -p /backups /run/myvita
chown postgres:postgres /backups /run/myvita
chmod 700 /backups /run/myvita
pgpass_escape() {
    local value="$1"
    value="${value//\\/\\\\}"
    printf '%s' "${value//:/\\:}"
}
printf '%s:%s:%s:%s:%s\n' \
    "$(pgpass_escape "$DB_HOST")" \
    "$(pgpass_escape "$DB_PORT")" \
    "$(pgpass_escape "$DB_NAME")" \
    "$(pgpass_escape "$DB_USER")" \
    "$(pgpass_escape "$POSTGRES_PASSWORD")" > /run/myvita/pgpass
chmod 600 /run/myvita/pgpass
chown postgres:postgres /run/myvita/pgpass
export PGPASSFILE=/run/myvita/pgpass

cat > /etc/crontabs/postgres <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
TZ=${TZ}
DB_HOST=${DB_HOST}
DB_PORT=${DB_PORT}
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
PGPASSFILE=/run/myvita/pgpass
BACKUP_RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-14}
${BACKUP_SCHEDULE} /opt/myvita/run_scheduled_backup.sh >> /proc/1/fd/1 2>> /proc/1/fd/2
EOF
chmod 600 /etc/crontabs/postgres

if [ "${BACKUP_RUN_ON_START:-true}" = "true" ]; then
    su-exec postgres /opt/myvita/run_scheduled_backup.sh
fi

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Backup scheduler started: schedule='${BACKUP_SCHEDULE}' timezone=${TZ} retention_days=${BACKUP_RETENTION_DAYS:-14}"
exec crond -f -l 5 -c /etc/crontabs
