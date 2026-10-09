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
command -v age >/dev/null && command -v age-keygen >/dev/null \
    || { echo "ERROR: age and age-keygen are required for these tests." >&2; exit 1; }
identity="${test_root}/backup.key"; wrong_identity="${test_root}/wrong.key"
age-keygen -o "$identity" 2>/dev/null; age-keygen -o "$wrong_identity" 2>/dev/null
OFFSITE_AGE_RECIPIENT="$(age-keygen -y "$identity")"
export OFFSITE_AGE_RECIPIENT
export OFFSITE_AGE_IDENTITY_FILE="$identity"
dump="${backups}/myvita_20260925T000000Z.dump"
printf 'valid archive fixture\n' > "$dump"
(cd "$backups" && sha256sum "$(basename "$dump")" > "$(basename "$dump").sha256")

# Encryption is mandatory: without a recipient nothing is uploaded.
if OFFSITE_AGE_RECIPIENT='' "${repo_root}/scripts/upload_offsite_backup.sh" "$dump" >/dev/null 2>&1; then
    echo "ERROR: an unencrypted upload was allowed without OFFSITE_AGE_RECIPIENT" >&2; exit 1
fi
if OFFSITE_AGE_RECIPIENT=age1notakey "${repo_root}/scripts/upload_offsite_backup.sh" "$dump" >/dev/null 2>&1; then
    echo "ERROR: an invalid age recipient was accepted" >&2; exit 1
fi
[ -z "$(find "$store" -type f)" ] || { echo "ERROR: a refused upload left objects behind" >&2; exit 1; }

"${repo_root}/scripts/upload_offsite_backup.sh" "$dump" >/dev/null
object="${store}/myvita/postgres/$(basename "$dump").age"
[ -s "$object" ] && [ -s "${object}.sha256" ]
[ ! -e "${store}/myvita/postgres/$(basename "$dump")" ] || { echo "ERROR: plaintext object uploaded" >&2; exit 1; }
[ "$(head -c 21 "$object")" = "age-encryption.org/v1" ] || { echo "ERROR: off-site object is not age-encrypted" >&2; exit 1; }
if grep -q 'valid archive fixture' "$object"; then echo "ERROR: plaintext visible in off-site object" >&2; exit 1; fi
[ -z "$(find "$backups" -name '.offsite-upload.*')" ] || { echo "ERROR: encryption work dir left behind" >&2; exit 1; }

download_dir="${test_root}/download"
"${repo_root}/scripts/download_offsite_backup.sh" "myvita/postgres/$(basename "$dump").age" "$download_dir" >/dev/null
(cd "$download_dir" && sha256sum -c "$(basename "$dump").sha256" >/dev/null)
cmp -s "$dump" "${download_dir}/$(basename "$dump")" || { echo "ERROR: decrypted backup differs from the original" >&2; exit 1; }

# Restore without the private key, or with the wrong one, must fail and publish nothing.
if OFFSITE_AGE_IDENTITY_FILE='' "${repo_root}/scripts/download_offsite_backup.sh" "myvita/postgres/$(basename "$dump").age" "${test_root}/nokey" >/dev/null 2>&1; then
    echo "ERROR: encrypted download succeeded without a key" >&2; exit 1
fi
if OFFSITE_AGE_IDENTITY_FILE="$wrong_identity" "${repo_root}/scripts/download_offsite_backup.sh" "myvita/postgres/$(basename "$dump").age" "${test_root}/wrongkey" >/dev/null 2>&1; then
    echo "ERROR: encrypted download succeeded with the wrong key" >&2; exit 1
fi
[ -z "$(find "${test_root}/nokey" "${test_root}/wrongkey" -type f 2>/dev/null)" ] || { echo "ERROR: a failed decryption left files behind" >&2; exit 1; }

# Explicit test-store escape hatch still uploads plaintext (legacy layout).
plain_store_check="${store}/myvita/postgres/$(basename "$dump")"
OFFSITE_AGE_RECIPIENT='' OFFSITE_ALLOW_PLAINTEXT=true "${repo_root}/scripts/upload_offsite_backup.sh" "$dump" >/dev/null
[ -s "$plain_store_check" ] && rm -f "$plain_store_check" "${plain_store_check}.sha256"

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
[ -s "${store}/myvita/documents/$(basename "$documents").age" ] && [ -s "${store}/myvita/documents/$(basename "$documents").age.sha256" ]
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
cmp -s "$documents" "${test_root}/latest/$(basename "$documents")" || { echo "ERROR: decrypted documents archive differs" >&2; exit 1; }

# Retention: expired legacy and new-layout objects go; the newest of each kind,
# anything outside the prefix and unrelated names under the prefix stay.
add_object() { mkdir -p "$(dirname "${store}/$1")"; printf old > "${store}/$1"; printf sum > "${store}/$1.sha256"; }
add_object myvita/myvita_20000101T000000Z.dump
add_object myvita/postgres/myvita_20000102T000000Z.dump
add_object myvita/documents/myvita_documents_20000101T000000Z.tar.gz
add_object myvita/postgres/myvita_20000104T000000Z.dump.age
add_object myvita/documents/myvita_documents_20000104T000000Z.tar.gz.age
add_object other-app/myvita_20000101T000000Z.dump
add_object myvita/notes/myvita_20000101T000000Z.dump
printf keep > "${store}/myvita/unrelated.txt"
"${repo_root}/scripts/prune_offsite_backups.sh" >/dev/null
[ ! -e "${store}/myvita/myvita_20000101T000000Z.dump" ] && [ ! -e "${store}/myvita/myvita_20000101T000000Z.dump.sha256" ]
[ ! -e "${store}/myvita/postgres/myvita_20000102T000000Z.dump" ]
[ ! -e "${store}/myvita/documents/myvita_documents_20000101T000000Z.tar.gz" ]
[ ! -e "${store}/myvita/postgres/myvita_20000104T000000Z.dump.age" ] && [ ! -e "${store}/myvita/postgres/myvita_20000104T000000Z.dump.age.sha256" ]
[ ! -e "${store}/myvita/documents/myvita_documents_20000104T000000Z.tar.gz.age" ]
[ -e "${store}/myvita/postgres/$(basename "$dump").age" ] && [ -e "${store}/myvita/documents/$(basename "$documents").age" ]
[ -e "${store}/other-app/myvita_20000101T000000Z.dump" ] && [ -e "${store}/myvita/notes/myvita_20000101T000000Z.dump" ]
[ -e "${store}/myvita/unrelated.txt" ]

# Only old backups left: the newest of each kind is still kept.
rm -f "${store}/myvita/postgres/$(basename "$dump")"*
add_object myvita/postgres/myvita_20000103T000000Z.dump.age
"${repo_root}/scripts/prune_offsite_backups.sh" >/dev/null
[ -e "${store}/myvita/postgres/myvita_20000103T000000Z.dump.age" ]

if OFFSITE_S3_PREFIX=/ "${repo_root}/scripts/prune_offsite_backups.sh" >/dev/null 2>&1; then
    echo "ERROR: pruning with an empty prefix was allowed" >&2; exit 1
fi

echo "Off-site backup script tests passed."
