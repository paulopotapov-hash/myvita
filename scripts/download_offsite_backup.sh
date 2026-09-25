#!/usr/bin/env bash
set -euo pipefail
umask 077

object_key="${1:-}"
output_dir="${2:-/backups/recovery}"
: "${OFFSITE_S3_BUCKET:?OFFSITE_S3_BUCKET is required}"
if [ -z "${AWS_ACCESS_KEY_ID:-}" ] && [ -z "${AWS_SHARED_CREDENTIALS_FILE:-}" ]; then
    echo "ERROR: AWS credentials are required." >&2; exit 1
fi
[[ "$object_key" == */myvita_*.dump ]] || { echo "ERROR: expected an off-site myvita dump key." >&2; exit 1; }

aws_cmd() {
    if [ -n "${OFFSITE_S3_ENDPOINT:-}" ]; then aws --endpoint-url "$OFFSITE_S3_ENDPOINT" "$@"; else aws "$@"; fi
}
export AWS_DEFAULT_REGION="${OFFSITE_S3_REGION:-us-east-1}"
mkdir -p "$output_dir"; chmod 700 "$output_dir"
dump_file="${output_dir}/$(basename "$object_key")"
tmp_dump="${dump_file}.tmp"
tmp_checksum="${dump_file}.sha256.tmp"
publish_checksum="${dump_file}.sha256.publish.tmp"
[ ! -e "$dump_file" ] && [ ! -e "${dump_file}.sha256" ] || { echo "ERROR: recovery destination already exists." >&2; exit 1; }
trap 'rm -f "$tmp_dump" "$tmp_checksum" "$publish_checksum"' EXIT INT TERM

aws_cmd s3 cp "s3://${OFFSITE_S3_BUCKET}/${object_key}" "$tmp_dump" --only-show-errors
aws_cmd s3 cp "s3://${OFFSITE_S3_BUCKET}/${object_key}.sha256" "$tmp_checksum" --only-show-errors
expected_digest="$(awk 'NR == 1 {print $1}' "$tmp_checksum")"
actual_digest="$(sha256sum "$tmp_dump" | awk '{print $1}')"
[ -n "$expected_digest" ] && [ "$expected_digest" = "$actual_digest" ] || { echo "ERROR: downloaded checksum does not match." >&2; exit 1; }
pg_restore --list "$tmp_dump" >/dev/null
printf '%s  %s\n' "$actual_digest" "$(basename "$dump_file")" > "$publish_checksum"
mv "$publish_checksum" "${dump_file}.sha256"
if ! mv "$tmp_dump" "$dump_file"; then
    rm -f "${dump_file}.sha256"
    exit 1
fi
rm -f "$tmp_checksum"
echo "Off-site download verified: ${dump_file}"
