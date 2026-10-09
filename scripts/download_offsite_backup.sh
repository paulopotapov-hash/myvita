#!/usr/bin/env bash
#
# Downloads verified backups from S3-compatible off-site storage, without
# needing anything from the original host.
#
# Usage:
#   download_offsite_backup.sh <object_key> [output_dir]
#       one object, e.g. myvita/postgres/myvita_20260101T030000Z.dump
#       (legacy flat keys such as myvita/myvita_<ts>.dump are also accepted)
#   download_offsite_backup.sh --latest [output_dir]
#       the newest PostgreSQL dump AND the newest documents archive under
#       $OFFSITE_S3_PREFIX (documents only if any exist)
#
# Each object is downloaded with its .sha256, the digest and archive are
# verified, and only then is it published under its final name in
# output_dir (default /backups/recovery). Existing files are never overwritten.
#
# Encrypted objects (<name>.age, see upload_offsite_backup.sh) are verified
# against their .sha256 (checksum of the ciphertext), decrypted with the age
# private key in OFFSITE_AGE_IDENTITY_FILE, verified again as a dump/archive
# and published under the plain name (without .age).
#
set -euo pipefail
umask 077

: "${OFFSITE_S3_BUCKET:?OFFSITE_S3_BUCKET is required}"
if [ -z "${AWS_ACCESS_KEY_ID:-}" ] && [ -z "${AWS_SHARED_CREDENTIALS_FILE:-}" ]; then
    echo "ERROR: AWS credentials are required." >&2; exit 1
fi

aws_cmd() {
    if [ -n "${OFFSITE_S3_ENDPOINT:-}" ]; then aws --endpoint-url "$OFFSITE_S3_ENDPOINT" "$@"; else aws "$@"; fi
}
export AWS_DEFAULT_REGION="${OFFSITE_S3_REGION:-us-east-1}"
prefix="${OFFSITE_S3_PREFIX:-myvita}"; prefix="${prefix#/}"; prefix="${prefix%/}"
ts='[0-9]{8}T[0-9]{6}Z'
dump_key_re="^(.+/)?myvita_${ts}\.dump(\.age)?$"
documents_key_re="^(.+/)?myvita_documents_${ts}\.tar\.gz(\.age)?$"

download_one() {
    local object_key="$1" output_dir="$2"
    if ! [[ "$object_key" =~ $dump_key_re ]] && ! [[ "$object_key" =~ $documents_key_re ]]; then
        echo "ERROR: expected an off-site myVita backup key: ${object_key}" >&2; return 1
    fi
    local encrypted=false
    if [[ "$object_key" == *.age ]]; then
        encrypted=true
        [ -n "${OFFSITE_AGE_IDENTITY_FILE:-}" ] && [ -r "${OFFSITE_AGE_IDENTITY_FILE}" ] \
            || { echo "ERROR: ${object_key} is encrypted; set OFFSITE_AGE_IDENTITY_FILE to a readable age private key file." >&2; return 1; }
        command -v age >/dev/null || { echo "ERROR: age is not installed." >&2; return 1; }
    fi
    mkdir -p "$output_dir"; chmod 700 "$output_dir"
    local plain_name; plain_name="$(basename "$object_key")"; plain_name="${plain_name%.age}"
    local file="${output_dir}/${plain_name}"
    local tmp_file="${file}.tmp" tmp_checksum="${file}.sha256.tmp" publish_checksum="${file}.sha256.publish.tmp"
    local tmp_plain="${file}.plain.tmp"
    [ ! -e "$file" ] && [ ! -e "${file}.sha256" ] || { echo "ERROR: recovery destination already exists: ${file}" >&2; return 1; }
    trap 'rm -f "$tmp_file" "$tmp_checksum" "$publish_checksum" "$tmp_plain"' RETURN

    aws_cmd s3 cp "s3://${OFFSITE_S3_BUCKET}/${object_key}" "$tmp_file" --only-show-errors \
        || { echo "ERROR: could not download ${object_key}" >&2; return 1; }
    aws_cmd s3 cp "s3://${OFFSITE_S3_BUCKET}/${object_key}.sha256" "$tmp_checksum" --only-show-errors \
        || { echo "ERROR: could not download the checksum for ${object_key}" >&2; return 1; }
    local expected actual
    expected="$(awk 'NR == 1 {print $1}' "$tmp_checksum")"
    actual="$(sha256sum "$tmp_file" | awk '{print $1}')"
    [ -n "$expected" ] && [ "$expected" = "$actual" ] || { echo "ERROR: downloaded checksum does not match: ${object_key}" >&2; return 1; }
    if [ "$encrypted" = true ]; then
        age -d -i "$OFFSITE_AGE_IDENTITY_FILE" -o "$tmp_plain" "$tmp_file" \
            || { echo "ERROR: could not decrypt ${object_key} (wrong key or damaged object)" >&2; return 1; }
        mv "$tmp_plain" "$tmp_file"
        actual="$(sha256sum "$tmp_file" | awk '{print $1}')"
    fi
    if [[ "$plain_name" == *.dump ]]; then
        pg_restore --list "$tmp_file" >/dev/null || { echo "ERROR: downloaded dump is not readable" >&2; return 1; }
    else
        { gzip -t "$tmp_file" && tar -tzf "$tmp_file" >/dev/null; } || { echo "ERROR: downloaded documents archive is not readable" >&2; return 1; }
    fi
    printf '%s  %s\n' "$actual" "$(basename "$file")" > "$publish_checksum"
    mv "$publish_checksum" "${file}.sha256"
    if ! mv "$tmp_file" "$file"; then
        rm -f "${file}.sha256"
        return 1
    fi
    echo "Off-site download verified: ${file}"
}

newest_key() {
    # Newest by the UTC timestamp embedded in the object name.
    local regex="$1"
    aws_cmd s3api list-objects-v2 --bucket "$OFFSITE_S3_BUCKET" --prefix "${prefix}/" --query 'Contents[].Key' --output text \
        | tr '\t' '\n' | grep -E "$regex" \
        | sed -E 's#^(.*([0-9]{8}T[0-9]{6}Z).*)$#\2 \1#' \
        | sort | tail -n 1 | cut -d' ' -f2-
}

if [ "${1:-}" = "--latest" ]; then
    output_dir="${2:-/backups/recovery}"
    dump_key="$(newest_key "^${prefix}/(postgres/)?myvita_${ts}\.dump(\.age)?$" || true)"
    [ -n "$dump_key" ] || { echo "ERROR: no PostgreSQL backup found under ${prefix}/" >&2; exit 1; }
    download_one "$dump_key" "$output_dir"
    documents_key="$(newest_key "^${prefix}/documents/myvita_documents_${ts}\.tar\.gz(\.age)?$" || true)"
    if [ -n "$documents_key" ]; then
        download_one "$documents_key" "$output_dir"
    else
        echo "WARNING: no documents archive found under ${prefix}/documents/" >&2
    fi
    exit 0
fi

object_key="${1:-}"
[ -n "$object_key" ] || { echo "Usage: $0 <object_key>|--latest [output_dir]" >&2; exit 1; }
download_one "$object_key" "${2:-/backups/recovery}"
