#!/usr/bin/env bash
#
# Maintains the node-exporter textfile metrics for backups (myvita_backup.prom).
# Events update the relevant gauges and keep every other value.
#
# Usage: write_backup_metrics.sh <event> [size_bytes] [file_count]
#   init | local-success SIZE | local-failure | documents-success SIZE FILES |
#   documents-failure | offsite-success | offsite-failure |
#   recovery-success | recovery-failure
#
set -euo pipefail

event="${1:-init}"
size_bytes="${2:-0}"
file_count="${3:-0}"
metrics_dir="${BACKUP_METRICS_DIR:-/metrics}"
metrics_file="${metrics_dir}/myvita_backup.prom"
mkdir -p "$metrics_dir"

metric_value() {
    local name="$1"
    [ -f "$metrics_file" ] || { printf '0'; return; }
    awk -v metric="$name" '$1 == metric { print $2; found=1 } END { if (!found) print 0 }' "$metrics_file"
}
for value in "$size_bytes" "$file_count"; do
    [[ "$value" =~ ^[0-9]+$ ]] || { echo "ERROR: metric values must be non-negative integers" >&2; exit 1; }
done

local_timestamp="$(metric_value myvita_backup_last_success_timestamp_seconds)"
local_success="$(metric_value myvita_backup_last_run_success)"
local_size="$(metric_value myvita_backup_last_size_bytes)"
documents_timestamp="$(metric_value myvita_documents_backup_last_success_timestamp_seconds)"
documents_success="$(metric_value myvita_documents_backup_last_run_success)"
documents_size="$(metric_value myvita_documents_backup_last_size_bytes)"
documents_files="$(metric_value myvita_documents_backup_last_file_count)"
offsite_timestamp="$(metric_value myvita_offsite_backup_last_success_timestamp_seconds)"
offsite_success="$(metric_value myvita_offsite_backup_last_run_success)"
recovery_timestamp="$(metric_value myvita_recovery_verification_last_success_timestamp_seconds)"
recovery_success="$(metric_value myvita_recovery_verification_last_run_success)"
case "$event" in
    init) ;;
    local-success) local_timestamp="$(date +%s)"; local_success=1; local_size="$size_bytes" ;;
    local-failure) local_success=0 ;;
    documents-success)
        documents_timestamp="$(date +%s)"; documents_success=1
        documents_size="$size_bytes"; documents_files="$file_count" ;;
    documents-failure) documents_success=0 ;;
    offsite-success) offsite_timestamp="$(date +%s)"; offsite_success=1 ;;
    offsite-failure) offsite_success=0 ;;
    recovery-success) recovery_timestamp="$(date +%s)"; recovery_success=1 ;;
    recovery-failure) recovery_success=0 ;;
    *) echo "ERROR: unknown metrics event: $event" >&2; exit 1 ;;
esac
offsite_enabled=0
[ "${OFFSITE_BACKUP_ENABLED:-false}" != "true" ] || offsite_enabled=1
documents_enabled=0
[ "${DOCUMENTS_BACKUP_ENABLED:-false}" != "true" ] || documents_enabled=1

tmp_file="$(mktemp "${metrics_dir}/.myvita_backup.prom.tmp.XXXXXX")"
cat > "$tmp_file" <<EOF
# HELP myvita_backup_last_success_timestamp_seconds Unix timestamp of the last successful local backup.
# TYPE myvita_backup_last_success_timestamp_seconds gauge
myvita_backup_last_success_timestamp_seconds ${local_timestamp}
# HELP myvita_backup_last_run_success Whether the last local backup run succeeded.
# TYPE myvita_backup_last_run_success gauge
myvita_backup_last_run_success ${local_success}
# HELP myvita_backup_last_size_bytes Size of the last successful PostgreSQL dump.
# TYPE myvita_backup_last_size_bytes gauge
myvita_backup_last_size_bytes ${local_size}
# HELP myvita_documents_backup_enabled Whether document storage backups are configured.
# TYPE myvita_documents_backup_enabled gauge
myvita_documents_backup_enabled ${documents_enabled}
# HELP myvita_documents_backup_last_success_timestamp_seconds Unix timestamp of the last verified documents archive.
# TYPE myvita_documents_backup_last_success_timestamp_seconds gauge
myvita_documents_backup_last_success_timestamp_seconds ${documents_timestamp}
# HELP myvita_documents_backup_last_run_success Whether the last documents backup succeeded.
# TYPE myvita_documents_backup_last_run_success gauge
myvita_documents_backup_last_run_success ${documents_success}
# HELP myvita_documents_backup_last_size_bytes Size of the last documents archive.
# TYPE myvita_documents_backup_last_size_bytes gauge
myvita_documents_backup_last_size_bytes ${documents_size}
# HELP myvita_documents_backup_last_file_count Number of stored documents in the last archive.
# TYPE myvita_documents_backup_last_file_count gauge
myvita_documents_backup_last_file_count ${documents_files}
# HELP myvita_offsite_backup_enabled Whether off-site backups are configured.
# TYPE myvita_offsite_backup_enabled gauge
myvita_offsite_backup_enabled ${offsite_enabled}
# HELP myvita_offsite_backup_last_success_timestamp_seconds Unix timestamp of the last verified off-site upload.
# TYPE myvita_offsite_backup_last_success_timestamp_seconds gauge
myvita_offsite_backup_last_success_timestamp_seconds ${offsite_timestamp}
# HELP myvita_offsite_backup_last_run_success Whether the last off-site upload succeeded.
# TYPE myvita_offsite_backup_last_run_success gauge
myvita_offsite_backup_last_run_success ${offsite_success}
# HELP myvita_recovery_verification_last_success_timestamp_seconds Unix timestamp of the last successful full recovery verification.
# TYPE myvita_recovery_verification_last_success_timestamp_seconds gauge
myvita_recovery_verification_last_success_timestamp_seconds ${recovery_timestamp}
# HELP myvita_recovery_verification_last_run_success Whether the last full recovery verification succeeded.
# TYPE myvita_recovery_verification_last_run_success gauge
myvita_recovery_verification_last_run_success ${recovery_success}
EOF
chmod 644 "$tmp_file"
mv "$tmp_file" "$metrics_file"
