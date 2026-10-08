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
    prefix=""
    while [ "$#" -gt 0 ]; do [ "$1" != --prefix ] || prefix="$2"; shift; done
    find "$MOCK_S3_ROOT" -type f -print | sed "s#^${MOCK_S3_ROOT}/##" | grep "^${prefix}" | paste -sd '\t' -
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
[ -s "${store}/myvita/postgres/$(basename "$dump")" ]
[ -s "${store}/myvita/postgres/$(basename "$dump").sha256" ]

download_dir="${test_root}/download"
"${repo_root}/scripts/download_offsite_backup.sh" "myvita/postgres/$(basename "$dump")" "$download_dir" >/dev/null
(cd "$download_dir" && sha256sum -c "$(basename "$dump").sha256" >/dev/null)

if MOCK_AWS_FAIL=true "${repo_root}/scripts/upload_offsite_backup.sh" "$dump" >/dev/null 2>&1; then
    echo "ERROR: failed off-site upload was reported as success" >&2; exit 1
fi
[ -s "$dump" ]

# Documents archives go to <prefix>/documents/ and are verified before upload.
documents="${backups}/myvita_documents_20260925T000000Z.tar.gz"
mkdir -p "${test_root}/docsrc/files"; printf 'fixture' > "${test_root}/docsrc/files/0123456789abcdef0123456789abcdef"
tar -C "${test_root}/docsrc" -czf "$documents" files
(cd "$backups" && sha256sum "$(basename "$documents")" > "$(basename "$documents").sha256")
"${repo_root}/scripts/upload_offsite_backup.sh" "$documents" >/dev/null
[ -s "${store}/myvita/documents/$(basename "$documents")" ] && [ -s "${store}/myvita/documents/$(basename "$documents").sha256" ]
printf 'not gzip' > "${backups}/myvita_documents_20260926T000000Z.tar.gz"
(cd "$backups" && sha256sum myvita_documents_20260926T000000Z.tar.gz > myvita_documents_20260926T000000Z.tar.gz.sha256)
if "${repo_root}/scripts/upload_offsite_backup.sh" "${backups}/myvita_documents_20260926T000000Z.tar.gz" >/dev/null 2>&1; then
    echo "ERROR: an unreadable documents archive was uploaded" >&2; exit 1
fi
if "${repo_root}/scripts/upload_offsite_backup.sh" "${test_root}/docsrc/files/0123456789abcdef0123456789abcdef" >/dev/null 2>&1; then
    echo "ERROR: a non-backup file was uploaded" >&2; exit 1
fi

"${repo_root}/scripts/download_offsite_backup.sh" --latest "${test_root}/latest" >/dev/null
[ -s "${test_root}/latest/$(basename "$dump")" ] && [ -s "${test_root}/latest/$(basename "$documents")" ]

# Retention: expired legacy and new-layout objects go; the newest of each kind,
# anything outside the prefix and unrelated names under the prefix stay.
add_object() { mkdir -p "$(dirname "${store}/$1")"; printf old > "${store}/$1"; printf sum > "${store}/$1.sha256"; }
add_object myvita/myvita_20000101T000000Z.dump
add_object myvita/postgres/myvita_20000102T000000Z.dump
add_object myvita/documents/myvita_documents_20000101T000000Z.tar.gz
add_object other-app/myvita_20000101T000000Z.dump
add_object myvita/notes/myvita_20000101T000000Z.dump
printf keep > "${store}/myvita/unrelated.txt"
"${repo_root}/scripts/prune_offsite_backups.sh" >/dev/null
[ ! -e "${store}/myvita/myvita_20000101T000000Z.dump" ] && [ ! -e "${store}/myvita/myvita_20000101T000000Z.dump.sha256" ]
[ ! -e "${store}/myvita/postgres/myvita_20000102T000000Z.dump" ]
[ ! -e "${store}/myvita/documents/myvita_documents_20000101T000000Z.tar.gz" ]
[ -e "${store}/myvita/postgres/$(basename "$dump")" ] && [ -e "${store}/myvita/documents/$(basename "$documents")" ]
[ -e "${store}/other-app/myvita_20000101T000000Z.dump" ] && [ -e "${store}/myvita/notes/myvita_20000101T000000Z.dump" ]
[ -e "${store}/myvita/unrelated.txt" ]

# Only old backups left: the newest of each kind is still kept.
rm -f "${store}/myvita/postgres/$(basename "$dump")"*
add_object myvita/postgres/myvita_20000103T000000Z.dump
"${repo_root}/scripts/prune_offsite_backups.sh" >/dev/null
[ -e "${store}/myvita/postgres/myvita_20000103T000000Z.dump" ]

if OFFSITE_S3_PREFIX=/ "${repo_root}/scripts/prune_offsite_backups.sh" >/dev/null 2>&1; then
    echo "ERROR: pruning with an empty prefix was allowed" >&2; exit 1
fi

echo "Off-site backup script tests passed."
