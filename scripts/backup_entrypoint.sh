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
mkdir -p /backups /metrics /run/myvita
chown postgres:postgres /backups /metrics /run/myvita
chmod 700 /backups /run/myvita
chmod 755 /metrics
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

if [ "${OFFSITE_BACKUP_ENABLED:-false}" = "true" ]; then
    : "${AWS_ACCESS_KEY_ID:?AWS_ACCESS_KEY_ID is required when off-site backup is enabled}"
    : "${AWS_SECRET_ACCESS_KEY:?AWS_SECRET_ACCESS_KEY is required when off-site backup is enabled}"
    if [ -z "${OFFSITE_AGE_RECIPIENT:-}" ] && [ "${OFFSITE_ALLOW_PLAINTEXT:-false}" != "true" ]; then
        echo "ERROR: OFFSITE_AGE_RECIPIENT (age public key) is required when off-site backup is enabled: backups are encrypted before upload." >&2
        exit 1
    fi
    cat > /run/myvita/aws_credentials <<EOF
[default]
aws_access_key_id=${AWS_ACCESS_KEY_ID}
aws_secret_access_key=${AWS_SECRET_ACCESS_KEY}
EOF
    chmod 600 /run/myvita/aws_credentials
    chown postgres:postgres /run/myvita/aws_credentials
fi

# The job runs as root only so it can read the backend-owned, read-only
# documents mount; database steps drop to the postgres user (see
# run_scheduled_backup.sh).
rm -f /etc/crontabs/postgres
cat > /etc/crontabs/root <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
TZ=${TZ}
DB_HOST=${DB_HOST}
DB_PORT=${DB_PORT}
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
PGPASSFILE=/run/myvita/pgpass
BACKUP_RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-14}
DOCUMENTS_BACKUP_ENABLED=${DOCUMENTS_BACKUP_ENABLED:-false}
DOCUMENT_STORAGE_DIR=${DOCUMENT_STORAGE_DIR:-/documents}
OFFSITE_BACKUP_ENABLED=${OFFSITE_BACKUP_ENABLED:-false}
OFFSITE_S3_BUCKET=${OFFSITE_S3_BUCKET:-}
OFFSITE_S3_PREFIX=${OFFSITE_S3_PREFIX:-myvita}
OFFSITE_S3_ENDPOINT=${OFFSITE_S3_ENDPOINT:-}
OFFSITE_S3_REGION=${OFFSITE_S3_REGION:-us-east-1}
OFFSITE_S3_SSE=${OFFSITE_S3_SSE:-AES256}
OFFSITE_RETENTION_DAYS=${OFFSITE_RETENTION_DAYS:-30}
OFFSITE_AGE_RECIPIENT=${OFFSITE_AGE_RECIPIENT:-}
OFFSITE_ALLOW_PLAINTEXT=${OFFSITE_ALLOW_PLAINTEXT:-false}
AWS_SHARED_CREDENTIALS_FILE=/run/myvita/aws_credentials
${BACKUP_SCHEDULE} /opt/myvita/run_scheduled_backup.sh >> /proc/1/fd/1 2>> /proc/1/fd/2
EOF
chmod 600 /etc/crontabs/root

/opt/myvita/write_backup_metrics.sh init

if [ "${BACKUP_RUN_ON_START:-true}" = "true" ]; then
    /opt/myvita/run_scheduled_backup.sh || echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) WARNING: initial backup run failed; the scheduler starts anyway" >&2
fi

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Backup scheduler started: schedule='${BACKUP_SCHEDULE}' timezone=${TZ} retention_days=${BACKUP_RETENTION_DAYS:-14} documents_backup=${DOCUMENTS_BACKUP_ENABLED:-false}"
exec crond -f -l 5 -c /etc/crontabs
