#!/usr/bin/env bash
#
# Uploads one completed local backup (+ its .sha256) to S3-compatible storage
# (AWS S3, Cloudflare R2, MinIO, ... via OFFSITE_S3_ENDPOINT).
#
#   myvita_<ts>.dump                  -> s3://$OFFSITE_S3_BUCKET/$OFFSITE_S3_PREFIX/postgres/
#   myvita_documents_<ts>.tar.gz      -> s3://$OFFSITE_S3_BUCKET/$OFFSITE_S3_PREFIX/documents/
#
# The local checksum and archive are verified first; the data object is
# uploaded before its .sha256, so a sidecar off-site always means the data
# upload finished. Both objects' sizes are checked after upload. Local files
# are never deleted here — local and off-site retention are independent.
#
# Usage: upload_offsite_backup.sh <backup_file>
#
set -euo pipefail

backup_file="${1:-}"
: "${OFFSITE_S3_BUCKET:?OFFSITE_S3_BUCKET is required}"
if [ -z "${AWS_ACCESS_KEY_ID:-}" ] && [ -z "${AWS_SHARED_CREDENTIALS_FILE:-}" ]; then
    echo "ERROR: AWS credentials are required." >&2; exit 1
fi
[ -n "$backup_file" ] && [ -s "$backup_file" ] || { echo "ERROR: valid backup file is required." >&2; exit 1; }

name="$(basename "$backup_file")"
if [[ "$name" =~ ^myvita_[0-9]{8}T[0-9]{6}Z\.dump$ ]]; then
    kind=postgres
elif [[ "$name" =~ ^myvita_documents_[0-9]{8}T[0-9]{6}Z\.tar\.gz$ ]]; then
    kind=documents
else
    echo "ERROR: not a myVita backup file name: ${name}" >&2; exit 1
fi

checksum_file="${backup_file}.sha256"
[ -s "$checksum_file" ] || { echo "ERROR: checksum is missing." >&2; exit 1; }
(cd "$(dirname "$backup_file")" && sha256sum -c "$(basename "$checksum_file")" >/dev/null) \
    || { echo "ERROR: local checksum verification failed; nothing was uploaded." >&2; exit 1; }
if [ "$kind" = postgres ]; then
    pg_restore --list "$backup_file" >/dev/null || { echo "ERROR: dump is not readable; nothing was uploaded." >&2; exit 1; }
else
    { gzip -t "$backup_file" && tar -tzf "$backup_file" >/dev/null; } \
        || { echo "ERROR: documents archive is not readable; nothing was uploaded." >&2; exit 1; }
fi

prefix="${OFFSITE_S3_PREFIX:-myvita}"
prefix="${prefix#/}"; prefix="${prefix%/}"
object_key="${prefix}/${kind}/${name}"
checksum_key="${object_key}.sha256"
aws_cmd() {
    if [ -n "${OFFSITE_S3_ENDPOINT:-}" ]; then aws --endpoint-url "$OFFSITE_S3_ENDPOINT" "$@"; else aws "$@"; fi
}
# Server-side encryption: AES256 (default) or aws:kms; "none" only for
# providers/test stores without SSE support — then encryption at rest is
# whatever the provider applies by default, and nothing here claims otherwise.
sse="${OFFSITE_S3_SSE:-AES256}"
case "$sse" in
    AES256|aws:kms|none) ;;
    *) echo "ERROR: OFFSITE_S3_SSE must be AES256, aws:kms or none." >&2; exit 1 ;;
esac
upload_object() {
    if [ "$sse" != none ]; then
        aws_cmd s3 cp "$1" "$2" --only-show-errors --sse "$sse"
    else
        aws_cmd s3 cp "$1" "$2" --only-show-errors
    fi
}
remote_size() {
    aws_cmd s3api head-object --bucket "$OFFSITE_S3_BUCKET" --key "$1" --query ContentLength --output text
}
export AWS_DEFAULT_REGION="${OFFSITE_S3_REGION:-us-east-1}"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Off-site upload started: kind=${kind} file=${name}"
upload_object "$backup_file" "s3://${OFFSITE_S3_BUCKET}/${object_key}" \
    || { echo "ERROR: off-site upload failed: ${object_key}" >&2; exit 1; }
upload_object "$checksum_file" "s3://${OFFSITE_S3_BUCKET}/${checksum_key}" \
    || { echo "ERROR: off-site checksum upload failed: ${checksum_key}" >&2; exit 1; }

local_size="$(wc -c < "$backup_file" | tr -d ' ')"
if [ "$(remote_size "$object_key")" != "$local_size" ]; then
    echo "ERROR: off-site object size verification failed: ${object_key}" >&2
    exit 1
fi
if [ "$(remote_size "$checksum_key")" != "$(wc -c < "$checksum_file" | tr -d ' ')" ]; then
    echo "ERROR: off-site checksum size verification failed: ${checksum_key}" >&2
    exit 1
fi
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Off-site upload completed successfully: key=${object_key} size=${local_size}"
