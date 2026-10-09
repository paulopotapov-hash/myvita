#!/usr/bin/env bash
#
# Backs up private document storage (DOCUMENT_STORAGE_DIR / the
# myvita_documents volume) into a verified, checksummed archive:
#
#   myvita_documents_YYYYMMDDTHHMMSSZ.tar.gz   (+ .sha256 sidecar)
#
# Archive layout:
#   files/<storage_key>   every stored object (32 lowercase hex chars)
#   MANIFEST.sha256       sha256sum-format digest of every file above
#   BACKUP_INFO           created_at, file_count, total_bytes
#
# Storage objects are immutable once written (the backend creates them with
# exclusive open and never rewrites them), so each one is copied to a
# private staging area and hashed there: an upload that is still being
# written can never produce a manifest that disagrees with the archive.
# Staged deletions (`.pending-*`) are deliberately excluded.
#
# Publication is atomic, exactly like backup_db.sh: temp archive -> gzip and
# tar integrity check -> manifest re-verified from the archive -> checksum
# sidecar -> rename. A partial archive is never visible under a final name.
#
# Usage: ./scripts/backup_documents.sh <storage_dir> [output_dir]
#
set -euo pipefail
umask 077

storage_dir="${1:-}"
output_dir="${2:-./backups}"
key_pattern='^[0-9a-f]{32}$'

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }
fail() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ERROR: $*" >&2; exit 1; }
file_size() { stat -c %s "$1" 2>/dev/null || stat -f %z "$1"; }

[ -n "$storage_dir" ] || { echo "Usage: $0 <storage_dir> [output_dir]" >&2; exit 2; }
[ -d "$storage_dir" ] || fail "document storage directory does not exist: ${storage_dir}"
[ -r "$storage_dir" ] && [ -x "$storage_dir" ] || fail "document storage directory is not readable: ${storage_dir}"

mkdir -p "$output_dir" || fail "cannot create output directory: ${output_dir}"
chmod 700 "$output_dir" || fail "cannot secure output directory: ${output_dir}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive="${output_dir}/myvita_documents_${timestamp}.tar.gz"
[ ! -e "$archive" ] || fail "backup already exists: $(basename "$archive")"
staging="$(mktemp -d "${output_dir}/.myvita_documents_${timestamp}.staging.XXXXXX")" \
    || fail "cannot create staging directory in ${output_dir}"
tmp_archive="${output_dir}/.myvita_documents_${timestamp}.tar.gz.tmp.$$"
tmp_checksum="${archive}.sha256.tmp"
started_at="$(date +%s)"

cleanup() { rm -rf "$staging" "$tmp_archive" "$tmp_checksum"; }
trap cleanup EXIT INT TERM

log "Documents backup started: file=$(basename "$archive")"

mkdir -p "${staging}/files"
file_count=0
total_bytes=0
skipped=0
for path in "$storage_dir"/* "$storage_dir"/.[!.]*; do
    [ -e "$path" ] || continue
    name="$(basename "$path")"
    if [ -f "$path" ] && [[ "$name" =~ $key_pattern ]]; then
        cp -p "$path" "${staging}/files/${name}" || fail "could not read stored object ${name}"
        file_count=$((file_count + 1))
        total_bytes=$((total_bytes + $(file_size "${staging}/files/${name}")))
    else
        # .pending-* (staged deletes) and anything unexpected are not documents.
        skipped=$((skipped + 1))
    fi
done

(
    cd "$staging"
    : > MANIFEST.sha256
    if [ "$file_count" -gt 0 ]; then
        find files -type f | LC_ALL=C sort | while IFS= read -r f; do sha256sum "$f"; done > MANIFEST.sha256
    fi
    printf 'created_at=%s\nfile_count=%s\ntotal_bytes=%s\n' "$timestamp" "$file_count" "$total_bytes" > BACKUP_INFO
) || fail "could not build manifest"

tar -C "$staging" -czf "$tmp_archive" files MANIFEST.sha256 BACKUP_INFO || fail "tar failed — no backup was produced"
[ -s "$tmp_archive" ] || fail "archive is empty"

# Integrity: valid gzip, readable tar, exactly the expected entries, and the
# manifest inside the archive matches the archived files.
gzip -t "$tmp_archive" || fail "archive failed gzip integrity check"
listing="$(tar -tzf "$tmp_archive")" || fail "archive cannot be listed"
listed_files="$(grep -c '^files/[0-9a-f]\{32\}$' <<< "$listing" || true)"
[ "$listed_files" = "$file_count" ] || fail "archive lists ${listed_files} files, expected ${file_count}"
check_dir="$(mktemp -d "${staging}/verify.XXXXXX")"
tar -C "$check_dir" -xzf "$tmp_archive" || fail "archive cannot be extracted"
(cd "$check_dir" && { [ ! -s MANIFEST.sha256 ] || sha256sum -c MANIFEST.sha256 >/dev/null; }) \
    || fail "archived files do not match the manifest"
rm -rf "$check_dir"

digest="$(sha256sum "$tmp_archive" | awk '{print $1}')"
[ -n "$digest" ] || fail "checksum generation failed"
printf '%s  %s\n' "$digest" "$(basename "$archive")" > "$tmp_checksum"
mv "$tmp_checksum" "${archive}.sha256"
if ! mv "$tmp_archive" "$archive"; then
    rm -f "${archive}.sha256"
    fail "could not publish the completed backup"
fi

duration="$(( $(date +%s) - started_at ))"
log "Documents backup completed successfully: file=$(basename "$archive") files=${file_count} stored_bytes=${total_bytes} archive_bytes=$(file_size "$archive") skipped_entries=${skipped} duration_seconds=${duration}"
