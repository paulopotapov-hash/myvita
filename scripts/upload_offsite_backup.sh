#!/usr/bin/env bash
set -euo pipefail

dump_file="${1:-}"
: "${OFFSITE_S3_BUCKET:?OFFSITE_S3_BUCKET is required}"
if [ -z "${AWS_ACCESS_KEY_ID:-}" ] && [ -z "${AWS_SHARED_CREDENTIALS_FILE:-}" ]; then
    echo "ERROR: AWS credentials are required." >&2; exit 1
fi
[ -n "$dump_file" ] && [ -s "$dump_file" ] || { echo "ERROR: valid dump file is required." >&2; exit 1; }

checksum_file="${dump_file}.sha256"
[ -s "$checksum_file" ] || { echo "ERROR: checksum is missing." >&2; exit 1; }
(cd "$(dirname "$dump_file")" && sha256sum -c "$(basename "$checksum_file")" >/dev/null)
pg_restore --list "$dump_file" >/dev/null

prefix="${OFFSITE_S3_PREFIX:-myvita}"
prefix="${prefix#/}"; prefix="${prefix%/}"
object_key="${prefix}/$(basename "$dump_file")"
checksum_key="${object_key}.sha256"
aws_cmd() {
    if [ -n "${OFFSITE_S3_ENDPOINT:-}" ]; then aws --endpoint-url "$OFFSITE_S3_ENDPOINT" "$@"; else aws "$@"; fi
}
upload_object() {
    if [ -n "${OFFSITE_S3_SSE:-AES256}" ]; then
        aws_cmd s3 cp "$1" "$2" --only-show-errors --sse "${OFFSITE_S3_SSE:-AES256}"
    else
        aws_cmd s3 cp "$1" "$2" --only-show-errors
    fi
}
export AWS_DEFAULT_REGION="${OFFSITE_S3_REGION:-us-east-1}"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Off-site upload started: file=$(basename "$dump_file")"
upload_object "$dump_file" "s3://${OFFSITE_S3_BUCKET}/${object_key}"
upload_object "$checksum_file" "s3://${OFFSITE_S3_BUCKET}/${checksum_key}"

remote_size="$(aws_cmd s3api head-object --bucket "$OFFSITE_S3_BUCKET" --key "$object_key" --query ContentLength --output text)"
local_size="$(wc -c < "$dump_file" | tr -d ' ')"
if [ "$remote_size" != "$local_size" ]; then
    echo "ERROR: off-site object size verification failed." >&2
    exit 1
fi
aws_cmd s3api head-object --bucket "$OFFSITE_S3_BUCKET" --key "$checksum_key" >/dev/null
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Off-site upload completed successfully: key=${object_key} size=${local_size}"
