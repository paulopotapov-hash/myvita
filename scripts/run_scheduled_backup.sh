#!/usr/bin/env bash
#
# One scheduled backup run (cron in the backup container; never the API):
#
#   1. PostgreSQL dump          (as the unprivileged postgres user)
#   2. Documents archive        (DOCUMENTS_BACKUP_ENABLED=true; reads the
#                                read-only documents mount, which belongs to
#                                the backend's user, so this step needs root)
#   3. Off-site upload of the artefacts produced in THIS run (optional)
#   4. Off-site and local retention
#
# Order matters for consistency: the database is dumped BEFORE the documents
# are archived. Document files are written before their row commits and are
# never modified, so every document row in the dump already has its file when
# the archive starts. See docs/p7-backup-and-restore.md ("Consistency model").
#
# Each step records its own metrics; one failing step does not skip the
# others, but the run exits non-zero if anything failed.
#
set -uo pipefail

scripts_dir="${MYVITA_SCRIPTS_DIR:-/opt/myvita}"
backup_dir="${BACKUP_DIR:-/backups}"
status=0
as_postgres() { if [ "$(id -u)" = "0" ]; then su-exec postgres "$@"; else "$@"; fi; }
newest() { find "$backup_dir" -maxdepth 1 -type f -name "$1" | sort | tail -n 1; }
size_of() { wc -c < "$1" | tr -d ' '; }

before_dump="$(newest 'myvita_[0-9]*.dump')"
if as_postgres "${scripts_dir}/backup_db.sh" "$backup_dir"; then
    dump="$(newest 'myvita_[0-9]*.dump')"
    "${scripts_dir}/write_backup_metrics.sh" local-success "$(size_of "$dump")"
else
    dump=""
    "${scripts_dir}/write_backup_metrics.sh" local-failure
    status=1
fi
[ "$dump" != "$before_dump" ] || dump=""

documents_archive=""
if [ "${DOCUMENTS_BACKUP_ENABLED:-false}" = "true" ]; then
    if "${scripts_dir}/backup_documents.sh" "${DOCUMENT_STORAGE_DIR:-/documents}" "$backup_dir"; then
        documents_archive="$(newest 'myvita_documents_*.tar.gz')"
        if [ "$(id -u)" = "0" ]; then
            chown postgres:postgres "$documents_archive" "${documents_archive}.sha256"
        fi
        file_count="$(tar -tzf "$documents_archive" | grep -c '^files/[0-9a-f]' || true)"
        "${scripts_dir}/write_backup_metrics.sh" documents-success "$(size_of "$documents_archive")" "$file_count"
    else
        "${scripts_dir}/write_backup_metrics.sh" documents-failure
        status=1
    fi
fi

if [ "${OFFSITE_BACKUP_ENABLED:-false}" = "true" ]; then
    offsite_ok=true
    for artefact in "$dump" "$documents_archive"; do
        [ -n "$artefact" ] || continue
        "${scripts_dir}/upload_offsite_backup.sh" "$artefact" || offsite_ok=false
    done
    if [ "$offsite_ok" = true ] && [ -n "$dump" ]; then
        "${scripts_dir}/write_backup_metrics.sh" offsite-success
        "${scripts_dir}/prune_offsite_backups.sh" || status=1
    else
        # Nothing new to upload because a local step failed also counts as a failed off-site run.
        "${scripts_dir}/write_backup_metrics.sh" offsite-failure
        status=1
    fi
fi

as_postgres "${scripts_dir}/prune_backups.sh" "$backup_dir" || status=1
exit "$status"
