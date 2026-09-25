#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf "$test_root"' EXIT
fake_bin="${test_root}/bin"
store="${test_root}/store"
backups="${test_root}/backups"
mkdir -p "$fake_bin" "$store" "$backups"

cat > "${fake_bin}/pg_restore" <<'EOF'
#!/usr/bin/env bash
[ "${MOCK_RESTORE_FAIL:-false}" != "true" ]
EOF

cat > "${fake_bin}/aws" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
[ "${MOCK_AWS_FAIL:-false}" != "true" ] || exit 70
if [ "${1:-}" = "--endpoint-url" ]; then shift 2; fi
service="$1"; action="$2"; shift 2
uri_path() { printf '%s' "${1#s3://*/}"; }
if [ "$service" = s3 ] && [ "$action" = cp ]; then
    source="$1"; destination="$2"
    if [[ "$source" == s3://* ]]; then
        cp "${MOCK_S3_ROOT}/$(uri_path "$source")" "$destination"
    else
        target="${MOCK_S3_ROOT}/$(uri_path "$destination")"
        mkdir -p "$(dirname "$target")"; cp "$source" "$target"
    fi
elif [ "$service" = s3api ] && [ "$action" = head-object ]; then
    key=""
    content_length=false
    while [ "$#" -gt 0 ]; do
        [ "$1" != --key ] || key="$2"
        [ "$1" != ContentLength ] || content_length=true
        shift
    done
    [ -f "${MOCK_S3_ROOT}/${key}" ]
    if [ "$content_length" = true ]; then wc -c < "${MOCK_S3_ROOT}/${key}" | tr -d ' '; fi
elif [ "$service" = s3api ] && [ "$action" = list-objects-v2 ]; then
    query="$*"
    find "$MOCK_S3_ROOT" -type f -name '*.dump' -print | sed "s#^${MOCK_S3_ROOT}/##" | paste -sd '\t' -
elif [ "$service" = s3api ] && [ "$action" = delete-object ]; then
    key=""
    while [ "$#" -gt 0 ]; do [ "$1" != --key ] || key="$2"; shift; done
    rm -f "${MOCK_S3_ROOT}/${key}"
else
    echo "unexpected mock aws invocation: $service $action" >&2; exit 71
fi
EOF
chmod 0555 "${fake_bin}/aws" "${fake_bin}/pg_restore"

export PATH="${fake_bin}:$PATH" MOCK_S3_ROOT="$store"
export OFFSITE_S3_BUCKET=test-bucket OFFSITE_S3_PREFIX=myvita OFFSITE_RETENTION_DAYS=30
export AWS_ACCESS_KEY_ID=test-only AWS_SECRET_ACCESS_KEY=test-only
dump="${backups}/myvita_20260925T000000Z.dump"
printf 'valid archive fixture\n' > "$dump"
(cd "$backups" && sha256sum "$(basename "$dump")" > "$(basename "$dump").sha256")

"${repo_root}/scripts/upload_offsite_backup.sh" "$dump" >/dev/null
[ -s "${store}/myvita/$(basename "$dump")" ]
[ -s "${store}/myvita/$(basename "$dump").sha256" ]

download_dir="${test_root}/download"
"${repo_root}/scripts/download_offsite_backup.sh" "myvita/$(basename "$dump")" "$download_dir" >/dev/null
(cd "$download_dir" && sha256sum -c "$(basename "$dump").sha256" >/dev/null)

if MOCK_AWS_FAIL=true "${repo_root}/scripts/upload_offsite_backup.sh" "$dump" >/dev/null 2>&1; then
    echo "ERROR: failed off-site upload was reported as success" >&2; exit 1
fi
[ -s "$dump" ]

second="${store}/myvita/myvita_20000101T000000Z.dump"
printf old > "$second"; (cd "$(dirname "$second")" && sha256sum "$(basename "$second")" > "$(basename "$second").sha256")
"${repo_root}/scripts/prune_offsite_backups.sh" >/dev/null
[ "$(find "${store}/myvita" -type f -name '*.dump' | wc -l | tr -d ' ')" = 1 ]

echo "Off-site backup script tests passed."
