#!/usr/bin/env bash
#
# Documents backup/restore script tests on real files in a temporary
# directory (no database or Docker needed). Never touches a real volume.
#
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test_root="$(mktemp -d)"
trap 'chmod -R u+rwx "$test_root" 2>/dev/null; rm -rf "$test_root"' EXIT
storage="${test_root}/storage"
backups="${test_root}/backups"
mkdir -p "$storage"
chmod 700 "$storage"

fail() { echo "FAIL: $*" >&2; exit 1; }
expect_failure() {
    local label="$1"; shift
    if "$@" >"${test_root}/last.log" 2>&1; then fail "${label} unexpectedly succeeded"; fi
}
mode_of() { stat -c %a "$1" 2>/dev/null || stat -f %Lp "$1"; }
digest_list() { (cd "$1" && find . -maxdepth 1 -type f -name '[0-9a-f]*' | LC_ALL=C sort | while IFS= read -r f; do sha256sum "$f"; done); }

# Representative storage: binary + text objects, a staged delete and a stray file.
key1=0123456789abcdef0123456789abcdef
key2=fedcba9876543210fedcba9876543210
key3=aaaaaaaaaaaaaaaabbbbbbbbbbbbbbbb
printf '%%PDF-1.7\nsynthetic document\n' > "${storage}/${key1}"
head -c 70000 /dev/urandom > "${storage}/${key2}"
printf '' > "${storage}/${key3}"
printf 'being deleted' > "${storage}/.pending-11111111111111111111111111111111"
printf 'stray' > "${storage}/README"
chmod 600 "${storage}"/*
expected_digests="$(digest_list "$storage" | grep -E "${key1}|${key2}|${key3}")"

# --- backup -------------------------------------------------------------------
"${repo_root}/scripts/backup_documents.sh" "$storage" "$backups" > "${test_root}/backup.log"
grep -q 'Documents backup completed successfully' "${test_root}/backup.log"
grep -q 'files=3 ' "${test_root}/backup.log" || fail "expected 3 documents in the archive"
archive="$(find "$backups" -maxdepth 1 -name 'myvita_documents_*.tar.gz' -type f)"
[[ "$(basename "$archive")" =~ ^myvita_documents_[0-9]{8}T[0-9]{6}Z\.tar\.gz$ ]] || fail "unexpected archive name"
[ -s "${archive}.sha256" ] || fail "missing checksum sidecar"
(cd "$backups" && sha256sum -c "$(basename "${archive}.sha256")" >/dev/null) || fail "sidecar does not verify"
[ "$(mode_of "$archive")" = 600 ] && [ "$(mode_of "${archive}.sha256")" = 600 ] || fail "backup files must be 0600"
[ "$(mode_of "$backups")" = 700 ] || fail "backup directory must be 0700"
[ -z "$(find "$backups" -mindepth 1 -name '.*')" ] || fail "temporary files left behind"
listing="$(tar -tzf "$archive")"
grep -q '^MANIFEST.sha256$' <<< "$listing" && grep -q '^BACKUP_INFO$' <<< "$listing" || fail "manifest/info missing"
grep -q 'pending' <<< "$listing" && fail "staged deletes must not be archived"
grep -q 'README' <<< "$listing" && fail "non-document entries must not be archived"
grep -q "Documents content" "${test_root}/backup.log" && fail "log must not contain document content"
grep -q 'synthetic document' "${test_root}/backup.log" && fail "log must not contain document content"

# --- backup failures ------------------------------------------------------------
expect_failure "backup of missing storage" "${repo_root}/scripts/backup_documents.sh" "${test_root}/nope" "$backups"
grep -q 'does not exist' "${test_root}/last.log"
printf blocked > "${test_root}/not-a-dir"
expect_failure "backup into an invalid output path" "${repo_root}/scripts/backup_documents.sh" "$storage" "${test_root}/not-a-dir/out"
if [ "$(id -u)" != "0" ]; then
    mkdir -p "${test_root}/locked"; printf x > "${test_root}/locked/${key1}"; chmod 000 "${test_root}/locked"
    expect_failure "backup of unreadable storage" "${repo_root}/scripts/backup_documents.sh" "${test_root}/locked" "$backups"
    chmod 700 "${test_root}/locked"
fi
[ "$(find "$backups" -maxdepth 1 -name 'myvita_documents_*.tar.gz' | wc -l | tr -d ' ')" = 1 ] || fail "failed backups published archives"

# --- round trip: lose the storage, restore it -----------------------------------
rm -rf "$storage"
target="${test_root}/restored"
mkdir -p "$target"
"${repo_root}/scripts/restore_documents.sh" "$archive" "$target" > "${test_root}/restore.log"
grep -q "Documents restore target: ${target}" "${test_root}/restore.log" || fail "target not displayed"
[ "$(digest_list "$target")" = "$expected_digests" ] || fail "restored contents differ from the originals"
[ "$(find "$target" -mindepth 1 | wc -l | tr -d ' ')" = 3 ] || fail "restore produced unexpected entries"
[ "$(mode_of "$target")" = 700 ] || fail "restored directory must be 0700"
for f in "$target"/*; do [ "$(mode_of "$f")" = 600 ] || fail "restored file $(basename "$f") must be 0600"; done

# --- restore safety -------------------------------------------------------------
expect_failure "restore over populated storage" "${repo_root}/scripts/restore_documents.sh" "$archive" "$target"
grep -q 'Refusing to overwrite' "${test_root}/last.log"
printf 'newer object' > "${target}/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
"${repo_root}/scripts/restore_documents.sh" "$archive" "$target" --replace-existing >/dev/null
[ ! -e "${target}/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" ] || fail "--replace-existing did not replace"
[ "$(digest_list "$target")" = "$expected_digests" ] || fail "replacement restore differs from the originals"

empty_target="${test_root}/empty"; mkdir -p "$empty_target"
cp "$archive" "${test_root}/$(basename "$archive")"
cp "${archive}.sha256" "${test_root}/$(basename "$archive").sha256"
printf 'x' >> "${test_root}/$(basename "$archive")"
expect_failure "restore with checksum mismatch" "${repo_root}/scripts/restore_documents.sh" "${test_root}/$(basename "$archive")" "$empty_target"
grep -q 'checksum mismatch' "${test_root}/last.log"

corrupt_dir="${test_root}/corrupt"; mkdir -p "$corrupt_dir"
corrupt="${corrupt_dir}/myvita_documents_20000101T000000Z.tar.gz"
head -c 100 "$archive" > "$corrupt"
(cd "$corrupt_dir" && sha256sum "$(basename "$corrupt")" > "$(basename "$corrupt").sha256")
expect_failure "restore of a truncated archive" "${repo_root}/scripts/restore_documents.sh" "$corrupt" "$empty_target"

rm -f "${corrupt}.sha256"
expect_failure "restore without checksum" "${repo_root}/scripts/restore_documents.sh" "$corrupt" "$empty_target"
grep -q 'checksum sidecar missing' "${test_root}/last.log"

# A tampered archive with a matching sidecar but a broken manifest, and one with path traversal.
evil_src="${test_root}/evil"; mkdir -p "${evil_src}/files"
printf 'content' > "${evil_src}/files/${key1}"
printf '%s  files/%s\n' "$(printf other | sha256sum | awk '{print $1}')" "$key1" > "${evil_src}/MANIFEST.sha256"
printf 'created_at=x\nfile_count=1\ntotal_bytes=7\n' > "${evil_src}/BACKUP_INFO"
bad_manifest="${corrupt_dir}/myvita_documents_20000102T000000Z.tar.gz"
tar -C "$evil_src" -czf "$bad_manifest" files MANIFEST.sha256 BACKUP_INFO
(cd "$corrupt_dir" && sha256sum "$(basename "$bad_manifest")" > "$(basename "$bad_manifest").sha256")
expect_failure "restore with manifest mismatch" "${repo_root}/scripts/restore_documents.sh" "$bad_manifest" "$empty_target"
grep -q 'do not match the manifest' "${test_root}/last.log"
printf 'x' > "${test_root}/escape"
traversal="${corrupt_dir}/myvita_documents_20000103T000000Z.tar.gz"
tar -C "$evil_src" -czf "$traversal" files MANIFEST.sha256 BACKUP_INFO ../escape 2>/dev/null \
    || tar -C "$evil_src" -czf "$traversal" -P files MANIFEST.sha256 BACKUP_INFO "${test_root}/escape"
(cd "$corrupt_dir" && sha256sum "$(basename "$traversal")" > "$(basename "$traversal").sha256")
expect_failure "restore with unexpected archive entries" "${repo_root}/scripts/restore_documents.sh" "$traversal" "$empty_target"
grep -q 'unexpected entry' "${test_root}/last.log"
[ -z "$(ls -A "$empty_target")" ] || fail "a rejected restore modified the target"
expect_failure "restore of a non-myVita file name" "${repo_root}/scripts/restore_documents.sh" "${test_root}/escape" "$empty_target"
expect_failure "restore into a missing target" "${repo_root}/scripts/restore_documents.sh" "$archive" "${test_root}/missing-target"

# --- empty storage is a valid (empty) backup -----------------------------------
mkdir -p "${test_root}/empty-storage"
"${repo_root}/scripts/backup_documents.sh" "${test_root}/empty-storage" "${test_root}/empty-backups" | grep -q 'files=0 ' \
    || fail "empty storage backup"

# --- local retention covers documents archives, only myVita names ----------------
old="${backups}/myvita_documents_20000101T000000Z.tar.gz"
cp "$archive" "$old"; cp "${archive}.sha256" "${old}.sha256"
printf other > "${backups}/other_20000101.tar.gz"
touch -t 200001010000 "$old" "${old}.sha256" "${backups}/other_20000101.tar.gz"
BACKUP_RETENTION_DAYS=7 "${repo_root}/scripts/prune_backups.sh" "$backups" | grep -q 'removed=1' || fail "retention count"
[ ! -e "$old" ] && [ ! -e "${old}.sha256" ] && [ -e "$archive" ] && [ -e "${backups}/other_20000101.tar.gz" ] \
    || fail "retention removed the wrong files"

# --- metrics --------------------------------------------------------------------
metrics="${test_root}/metrics"
BACKUP_METRICS_DIR="$metrics" DOCUMENTS_BACKUP_ENABLED=true "${repo_root}/scripts/write_backup_metrics.sh" documents-success 1234 3
grep -q '^myvita_documents_backup_last_run_success 1$' "${metrics}/myvita_backup.prom"
grep -q '^myvita_documents_backup_last_size_bytes 1234$' "${metrics}/myvita_backup.prom"
grep -q '^myvita_documents_backup_last_file_count 3$' "${metrics}/myvita_backup.prom"
grep -q '^myvita_documents_backup_enabled 1$' "${metrics}/myvita_backup.prom"
BACKUP_METRICS_DIR="$metrics" "${repo_root}/scripts/write_backup_metrics.sh" documents-failure
grep -q '^myvita_documents_backup_last_run_success 0$' "${metrics}/myvita_backup.prom"
grep -q '^myvita_documents_backup_last_size_bytes 1234$' "${metrics}/myvita_backup.prom" || fail "failure must keep last good size"
BACKUP_METRICS_DIR="$metrics" "${repo_root}/scripts/write_backup_metrics.sh" recovery-success
grep -q '^myvita_recovery_verification_last_run_success 1$' "${metrics}/myvita_backup.prom"

echo "Documents backup script tests passed."
