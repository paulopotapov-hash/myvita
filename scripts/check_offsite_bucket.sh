#!/usr/bin/env bash
#
# Reports (read-only) how the off-site bucket is protected. It never changes
# bucket configuration: versioning and object lock must be enabled at the
# provider by its administrator.
#
#   OFFSITE_BUCKET bucket=<name> versioning=Enabled|Suspended|Disabled|Unknown object_lock=Enabled|Disabled|Unknown
#
# Exit code 0 when versioning is Enabled, 1 otherwise (so it can gate go-live
# checks), 2 on configuration errors.
#
set -euo pipefail

: "${OFFSITE_S3_BUCKET:?OFFSITE_S3_BUCKET is required}"
if [ -z "${AWS_ACCESS_KEY_ID:-}" ] && [ -z "${AWS_SHARED_CREDENTIALS_FILE:-}" ]; then
    echo "ERROR: AWS credentials are required." >&2; exit 2
fi
aws_cmd() {
    if [ -n "${OFFSITE_S3_ENDPOINT:-}" ]; then aws --endpoint-url "$OFFSITE_S3_ENDPOINT" "$@"; else aws "$@"; fi
}
export AWS_DEFAULT_REGION="${OFFSITE_S3_REGION:-us-east-1}"

if versioning="$(aws_cmd s3api get-bucket-versioning --bucket "$OFFSITE_S3_BUCKET" --query Status --output text 2>/dev/null)"; then
    case "$versioning" in Enabled|Suspended) ;; *) versioning=Disabled ;; esac
else
    versioning=Unknown
fi
if lock="$(aws_cmd s3api get-object-lock-configuration --bucket "$OFFSITE_S3_BUCKET" \
        --query ObjectLockConfiguration.ObjectLockEnabled --output text 2>/dev/null)"; then
    [ "$lock" = Enabled ] || lock=Disabled
else
    # Most providers answer "not found" when object lock was never configured.
    lock=Disabled
fi
echo "OFFSITE_BUCKET bucket=${OFFSITE_S3_BUCKET} versioning=${versioning} object_lock=${lock}"
[ "$versioning" = Enabled ]
