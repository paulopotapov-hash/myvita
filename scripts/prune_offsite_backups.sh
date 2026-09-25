#!/usr/bin/env bash
set -euo pipefail

: "${OFFSITE_S3_BUCKET:?OFFSITE_S3_BUCKET is required}"
retention_days="${OFFSITE_RETENTION_DAYS:-30}"
if ! [[ "$retention_days" =~ ^[0-9]+$ ]] || [ "$retention_days" -lt 1 ]; then
    echo "ERROR: OFFSITE_RETENTION_DAYS must be a positive integer." >&2
    exit 1
fi

prefix="${OFFSITE_S3_PREFIX:-myvita}"; prefix="${prefix#/}"; prefix="${prefix%/}"
aws_cmd() {
    if [ -n "${OFFSITE_S3_ENDPOINT:-}" ]; then aws --endpoint-url "$OFFSITE_S3_ENDPOINT" "$@"; else aws "$@"; fi
}
export AWS_DEFAULT_REGION="${OFFSITE_S3_REGION:-us-east-1}"
cutoff="$(date -u -d "${retention_days} days ago" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-"${retention_days}"d +%Y-%m-%dT%H:%M:%SZ)"
all_dumps=()
while IFS= read -r key; do [ -z "$key" ] || all_dumps+=("$key"); done < <(aws_cmd s3api list-objects-v2 --bucket "$OFFSITE_S3_BUCKET" --prefix "${prefix}/myvita_" --query 'Contents[].Key' --output text | tr '\t' '\n' | grep -E '/myvita_[0-9]{8}T[0-9]{6}Z\.dump$' || true)
expired=()
while IFS= read -r key; do [ -z "$key" ] || expired+=("$key"); done < <(aws_cmd s3api list-objects-v2 --bucket "$OFFSITE_S3_BUCKET" --prefix "${prefix}/myvita_" --query "Contents[?LastModified<=\`${cutoff}\`].Key" --output text | tr '\t' '\n' | grep -E '/myvita_[0-9]{8}T[0-9]{6}Z\.dump$' || true)

removed=0
remaining="${#all_dumps[@]}"
for key in "${expired[@]}"; do
    [ "$remaining" -gt 1 ] || break
    aws_cmd s3api delete-object --bucket "$OFFSITE_S3_BUCKET" --key "$key" >/dev/null
    aws_cmd s3api delete-object --bucket "$OFFSITE_S3_BUCKET" --key "${key}.sha256" >/dev/null
    removed=$((removed + 1)); remaining=$((remaining - 1))
done
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Off-site retention completed: removed=${removed} retention_days=${retention_days} remaining=${remaining}"
