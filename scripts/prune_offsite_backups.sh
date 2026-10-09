#!/usr/bin/env bash
#
# Off-site retention, independent of local retention.
#
# Deletes only objects that:
#   - are under "$OFFSITE_S3_PREFIX/" (which must be a plain, non-empty path), and
#   - exactly match one of the myVita backup names:
#       <prefix>/myvita_<ts>.dump                         (legacy flat layout)
#       <prefix>/postgres/myvita_<ts>.dump
#       <prefix>/documents/myvita_documents_<ts>.tar.gz
#   - carry a UTC timestamp in their name older than OFFSITE_RETENTION_DAYS.
# The newest PostgreSQL dump and the newest documents archive are always kept,
# however old. Each deleted object's .sha256 sidecar is deleted with it.
# Provider-side versioning/object lock (recommended) still protects deleted
# versions; this script does not change bucket configuration.
#
set -euo pipefail

: "${OFFSITE_S3_BUCKET:?OFFSITE_S3_BUCKET is required}"
retention_days="${OFFSITE_RETENTION_DAYS:-30}"
if ! [[ "$retention_days" =~ ^[0-9]+$ ]] || [ "$retention_days" -lt 1 ]; then
    echo "ERROR: OFFSITE_RETENTION_DAYS must be a positive integer." >&2
    exit 1
fi

prefix="${OFFSITE_S3_PREFIX:-myvita}"; prefix="${prefix#/}"; prefix="${prefix%/}"
if ! [[ "$prefix" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ ]] || [[ "$prefix" == *..* ]]; then
    echo "ERROR: OFFSITE_S3_PREFIX must be a non-empty plain path; refusing to prune." >&2
    exit 1
fi
escaped_prefix="$(printf '%s' "$prefix" | sed 's/[.]/\\./g')"
aws_cmd() {
    if [ -n "${OFFSITE_S3_ENDPOINT:-}" ]; then aws --endpoint-url "$OFFSITE_S3_ENDPOINT" "$@"; else aws "$@"; fi
}
export AWS_DEFAULT_REGION="${OFFSITE_S3_REGION:-us-east-1}"
cutoff="$(date -u -d "${retention_days} days ago" +%Y%m%dT%H%M%SZ 2>/dev/null || date -u -v-"${retention_days}"d +%Y%m%dT%H%M%SZ)"

listing="$(aws_cmd s3api list-objects-v2 --bucket "$OFFSITE_S3_BUCKET" --prefix "${prefix}/" --query 'Contents[].Key' --output text)" \
    || { echo "ERROR: could not list off-site objects." >&2; exit 1; }
keys="$(printf '%s\n' "$listing" | tr '\t' '\n' | sed '/^None$/d;/^$/d')"

removed=0
kept=0
for kind_re in "^${escaped_prefix}/(postgres/)?myvita_[0-9]{8}T[0-9]{6}Z\.dump$" \
               "^${escaped_prefix}/documents/myvita_documents_[0-9]{8}T[0-9]{6}Z\.tar\.gz$"; do
    # "<timestamp> <key>", oldest first.
    candidates="$(printf '%s\n' "$keys" | grep -E "$kind_re" \
        | sed -E 's#^(.*([0-9]{8}T[0-9]{6}Z).*)$#\2 \1#' | sort || true)"
    [ -n "$candidates" ] || continue
    newest="$(printf '%s\n' "$candidates" | tail -n 1 | cut -d' ' -f2-)"
    while IFS=' ' read -r stamp key; do
        if [ "$key" = "$newest" ] || [[ "$stamp" > "$cutoff" ]]; then
            kept=$((kept + 1)); continue
        fi
        aws_cmd s3api delete-object --bucket "$OFFSITE_S3_BUCKET" --key "$key" >/dev/null
        aws_cmd s3api delete-object --bucket "$OFFSITE_S3_BUCKET" --key "${key}.sha256" >/dev/null
        removed=$((removed + 1))
    done <<< "$candidates"
done
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Off-site retention completed: removed=${removed} kept=${kept} retention_days=${retention_days}"
