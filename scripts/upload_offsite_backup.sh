#!/usr/bin/env bash
#
# Uploads one completed local backup (+ its .sha256) to S3-compatible storage
# (AWS S3, Cloudflare R2, MinIO, ... via OFFSITE_S3_ENDPOINT).
#
#   myvita_<ts>.dump                  -> s3://$OFFSITE_S3_BUCKET/$OFFSITE_S3_PREFIX/postgres/
#   myvita_documents_<ts>.tar.gz      -> s3://$OFFSITE_S3_BUCKET/$OFFSITE_S3_PREFIX/documents/
#
# Client-side encryption: backups contain health data, so every object is
# encrypted with age (https://age-encryption.org) BEFORE it leaves the host
# and stored as <name>.age. OFFSITE_AGE_RECIPIENT holds one or more age public
# keys (space or comma separated, e.g. one per operator). The private keys
# never live on the server; restoring needs one of them
# (download_offsite_backup.sh, OFFSITE_AGE_IDENTITY_FILE). The .sha256 sidecar
# is the checksum of the encrypted object. Without a recipient the upload is
# refused, unless OFFSITE_ALLOW_PLAINTEXT=true (test stores only).
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

recipients="${OFFSITE_AGE_RECIPIENT:-}"
age_args=()
for recipient in ${recipients//,/ }; do
    if ! [[ "$recipient" =~ ^age1[02-9ac-hj-np-z]{58}$ ]]; then
        echo "ERROR: OFFSITE_AGE_RECIPIENT contains an invalid age public key; nothing was uploaded." >&2; exit 1
    fi
    age_args+=(-r "$recipient")
done
upload_source="$backup_file"
upload_checksum="$checksum_file"
suffix=""
if [ "${#age_args[@]}" -gt 0 ]; then
    command -v age >/dev/null || { echo "ERROR: age is not installed; nothing was uploaded." >&2; exit 1; }
    work_dir="$(mktemp -d "$(dirname "$backup_file")/.offsite-upload.XXXXXX")"
    trap 'rm -rf "$work_dir"' EXIT
    chmod 700 "$work_dir"
    encrypted="${work_dir}/${name}.age"
    (umask 077 && age "${age_args[@]}" -o "$encrypted" "$backup_file") \
        || { echo "ERROR: encryption failed; nothing was uploaded." >&2; exit 1; }
    [ "$(head -c 21 "$encrypted")" = "age-encryption.org/v1" ] \
        || { echo "ERROR: encrypted output is not an age file; nothing was uploaded." >&2; exit 1; }
    (cd "$work_dir" && sha256sum "${name}.age" > "${name}.age.sha256")
    upload_source="$encrypted"
    upload_checksum="${encrypted}.sha256"
    suffix=".age"
elif [ "${OFFSITE_ALLOW_PLAINTEXT:-false}" != "true" ]; then
    echo "ERROR: OFFSITE_AGE_RECIPIENT is required: backups contain health data and must be encrypted before upload. (OFFSITE_ALLOW_PLAINTEXT=true is for test stores only.)" >&2
    exit 1
fi

prefix="${OFFSITE_S3_PREFIX:-myvita}"
prefix="${prefix#/}"; prefix="${prefix%/}"
object_key="${prefix}/${kind}/${name}${suffix}"
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

encryption=none
[ -z "$suffix" ] || encryption=age
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Off-site upload started: kind=${kind} file=${name} encryption=${encryption}"
upload_object "$upload_source" "s3://${OFFSITE_S3_BUCKET}/${object_key}" \
    || { echo "ERROR: off-site upload failed: ${object_key}" >&2; exit 1; }
upload_object "$upload_checksum" "s3://${OFFSITE_S3_BUCKET}/${checksum_key}" \
    || { echo "ERROR: off-site checksum upload failed: ${checksum_key}" >&2; exit 1; }

local_size="$(wc -c < "$upload_source" | tr -d ' ')"
if [ "$(remote_size "$object_key")" != "$local_size" ]; then
    echo "ERROR: off-site object size verification failed: ${object_key}" >&2
    exit 1
fi
if [ "$(remote_size "$checksum_key")" != "$(wc -c < "$upload_checksum" | tr -d ' ')" ]; then
    echo "ERROR: off-site checksum size verification failed: ${checksum_key}" >&2
    exit 1
fi
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Off-site upload completed successfully: key=${object_key} size=${local_size} encryption=${encryption}"
