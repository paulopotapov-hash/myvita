#!/usr/bin/env bash
#
# Restores private document storage from an archive made by backup_documents.sh.
#
# Safety:
#   - the .sha256 sidecar is REQUIRED and checked before anything is extracted;
#   - every archive entry must be files/<32-hex key>, MANIFEST.sha256 or
#     BACKUP_INFO (no absolute paths, `..`, links or unexpected names);
#   - files are extracted to a private staging directory and checked against
#     the manifest before the target is touched;
#   - a target that already contains entries is refused unless
#     --replace-existing is given (then existing objects are removed only
#     after the new set has been fully verified);
#   - restored files are 0600 and the directory 0700, owned by --owner
#     UID:GID or, by default, by whoever owns the target directory (the
#     backend's `myvita` user on a volume the backend has already mounted).
#
# Usage:
#   ./scripts/restore_documents.sh <archive.tar.gz> <target_dir> [--replace-existing] [--owner UID:GID]
#
set -euo pipefail
umask 077

archive=""
target=""
replace_existing=false
owner=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --replace-existing) replace_existing=true; shift ;;
        --owner) owner="${2:?--owner needs UID:GID}"; shift 2 ;;
        -*) echo "ERROR: unknown option: $1" >&2; exit 2 ;;
        *)
            if [ -z "$archive" ]; then archive="$1"
            elif [ -z "$target" ]; then target="$1"
            else echo "ERROR: unexpected argument: $1" >&2; exit 2
            fi
            shift ;;
    esac
done

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }
fail() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ERROR: $*" >&2; exit 1; }

[ -n "$archive" ] && [ -n "$target" ] || {
    echo "Usage: $0 <archive.tar.gz> <target_dir> [--replace-existing] [--owner UID:GID]" >&2; exit 2; }
[[ "$(basename "$archive")" =~ ^myvita_documents_[0-9]{8}T[0-9]{6}Z\.tar\.gz$ ]] \
    || fail "not a myVita documents archive name: $(basename "$archive")"
[ -s "$archive" ] || fail "archive not found or empty: ${archive}"
[ -n "$owner" ] && ! [[ "$owner" =~ ^[0-9]+:[0-9]+$ ]] && fail "--owner must be numeric UID:GID"
[ -d "$target" ] || fail "target directory does not exist: ${target} (create/mount it first)"
target="$(cd "$target" && pwd)"

log "Documents restore target: ${target}"

checksum_file="${archive}.sha256"
[ -s "$checksum_file" ] || fail "checksum sidecar missing: $(basename "$checksum_file"); refusing to restore an unverifiable archive"
(cd "$(dirname "$archive")" && sha256sum -c "$(basename "$checksum_file")" >/dev/null) \
    || fail "checksum mismatch; restore was not started"
gzip -t "$archive" || fail "archive is corrupt (gzip); restore was not started"
listing="$(tar -tzvf "$archive")" || fail "archive cannot be listed; restore was not started"
names="$(tar -tzf "$archive")"
while IFS= read -r entry; do
    [[ "$entry" =~ ^(files/?|files/[0-9a-f]{32}|MANIFEST\.sha256|BACKUP_INFO)$ ]] \
        || fail "archive contains an unexpected entry; restore was not started"
done <<< "$names"
# Only regular files and the files/ directory: no symlinks, hardlinks or devices.
if grep -v -E '^[-d]' <<< "$listing" | grep -q .; then
    fail "archive contains non-regular entries; restore was not started"
fi

existing="$(find "$target" -mindepth 1 -maxdepth 1 ! -name '.myvita-restore-*' | wc -l | tr -d ' ')"
if [ "$existing" != "0" ] && [ "$replace_existing" != "true" ]; then
    fail "target already contains ${existing} entries. Refusing to overwrite documents; pass --replace-existing to replace them"
fi

if [ -z "$owner" ]; then
    owner="$(stat -c '%u:%g' "$target" 2>/dev/null || stat -f '%u:%g' "$target")"
fi

staging="$(mktemp -d "${target}/.myvita-restore-XXXXXX")" || fail "cannot create staging directory in target"
trap 'rm -rf "$staging"' EXIT INT TERM
tar -C "$staging" -xzf "$archive" || fail "extraction failed; target was not modified"
(cd "$staging" && { [ ! -s MANIFEST.sha256 ] || sha256sum -c MANIFEST.sha256 >/dev/null; }) \
    || fail "extracted files do not match the manifest; target was not modified"
expected_count="$(sed -n 's/^file_count=//p' "${staging}/BACKUP_INFO")"
actual_count="$(find "${staging}/files" -type f 2>/dev/null | wc -l | tr -d ' ')"
[ "$expected_count" = "$actual_count" ] || fail "archive has ${actual_count} files but BACKUP_INFO says ${expected_count}"

if [ "$existing" != "0" ]; then
    log "Replacing ${existing} existing entries (--replace-existing)"
    find "$target" -mindepth 1 -maxdepth 1 ! -name "$(basename "$staging")" -exec rm -rf {} +
fi

restored=0
if [ -d "${staging}/files" ]; then
    for path in "${staging}/files"/*; do
        [ -e "$path" ] || continue
        chmod 0600 "$path"
        chown "$owner" "$path" 2>/dev/null || [ "$(id -u)" != "0" ] || fail "could not set owner ${owner}"
        mv "$path" "${target}/$(basename "$path")"
        restored=$((restored + 1))
    done
fi
chmod 0700 "$target"
chown "$owner" "$target" 2>/dev/null || true

log "Documents restore completed: target=${target} files=${restored} owner=${owner} source=$(basename "$archive")"
echo "Next: run scripts/verify_documents_storage.sh against the restored database to confirm every document record has its file."
