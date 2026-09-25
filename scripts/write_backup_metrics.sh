#!/usr/bin/env bash
set -euo pipefail

event="${1:-init}"
metrics_dir="${BACKUP_METRICS_DIR:-/metrics}"
metrics_file="${metrics_dir}/myvita_backup.prom"
mkdir -p "$metrics_dir"

metric_value() {
    local name="$1"
    [ -f "$metrics_file" ] || { printf '0'; return; }
    awk -v metric="$name" '$1 == metric { print $2; found=1 } END { if (!found) print 0 }' "$metrics_file"
}

local_timestamp="$(metric_value myvita_backup_last_success_timestamp_seconds)"
offsite_timestamp="$(metric_value myvita_offsite_backup_last_success_timestamp_seconds)"
local_success="$(metric_value myvita_backup_last_run_success)"
offsite_success="$(metric_value myvita_offsite_backup_last_run_success)"
case "$event" in
    init) ;;
    local-success) local_timestamp="$(date +%s)"; local_success=1 ;;
    local-failure) local_success=0 ;;
    offsite-success) offsite_timestamp="$(date +%s)"; offsite_success=1 ;;
    offsite-failure) offsite_success=0 ;;
    *) echo "ERROR: unknown metrics event: $event" >&2; exit 1 ;;
esac
offsite_enabled=0
[ "${OFFSITE_BACKUP_ENABLED:-false}" != "true" ] || offsite_enabled=1

tmp_file="$(mktemp "${metrics_dir}/.myvita_backup.prom.tmp.XXXXXX")"
cat > "$tmp_file" <<EOF
# HELP myvita_backup_last_success_timestamp_seconds Unix timestamp of the last successful local backup.
# TYPE myvita_backup_last_success_timestamp_seconds gauge
myvita_backup_last_success_timestamp_seconds ${local_timestamp}
# HELP myvita_backup_last_run_success Whether the last local backup run succeeded.
# TYPE myvita_backup_last_run_success gauge
myvita_backup_last_run_success ${local_success}
# HELP myvita_offsite_backup_enabled Whether off-site backups are configured.
# TYPE myvita_offsite_backup_enabled gauge
myvita_offsite_backup_enabled ${offsite_enabled}
# HELP myvita_offsite_backup_last_success_timestamp_seconds Unix timestamp of the last verified off-site upload.
# TYPE myvita_offsite_backup_last_success_timestamp_seconds gauge
myvita_offsite_backup_last_success_timestamp_seconds ${offsite_timestamp}
# HELP myvita_offsite_backup_last_run_success Whether the last off-site upload succeeded.
# TYPE myvita_offsite_backup_last_run_success gauge
myvita_offsite_backup_last_run_success ${offsite_success}
EOF
chmod 644 "$tmp_file"
mv "$tmp_file" "$metrics_file"
