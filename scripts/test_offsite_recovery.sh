#!/usr/bin/env bash
#
# Complete disaster-recovery test: PostgreSQL + private documents, through a
# real S3-compatible object store, on throwaway infrastructure only.
#
#   1. source PostgreSQL + documents volume + backend; realistic data created
#      through the real API (clinic, staff, patient, documents, messages)
#   2. the shipped scheduled job: pg_dump -> documents archive -> off-site upload
#   3. off-site failure cases (bad credentials, missing/tampered objects,
#      retention boundaries, bucket protection report)
#   4. destroy the whole source environment (DB, documents volume, local backups)
#   5. download the latest backup set from the object store only
#   6. verify_restore.sh (isolated DB + documents + referential integrity)
#   7. real restore into a fresh DB + fresh documents volume, orphan check,
#      start a backend on the recovered data and download every document
#
# The object store is SeaweedFS (S3 API, access-key auth) running only on a
# private Docker network with test-only credentials; it has no route to any
# real bucket. Requires docker, curl and python3. Never touches developer data.
#
# Usage: ./scripts/test_offsite_recovery.sh
#
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sfx="$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
net="myvita-dr-${sfx}"
s3="myvita-dr-s3-${sfx}"
src_db="myvita-dr-srcdb-${sfx}"
src_api="myvita-dr-srcapi-${sfx}"
dst_db="myvita-dr-dstdb-${sfx}"
dst_api="myvita-dr-dstapi-${sfx}"
src_docs="myvita-dr-srcdocs-${sfx}"
dst_docs="myvita-dr-dstdocs-${sfx}"
backup_image="myvita-backup:dr-test-${sfx}"
backend_image="myvita-backend:dr-test-${sfx}"
store_image="chrislusf/seaweedfs:3.80"
work="$(mktemp -d)"
db_password="dr-test-only-${sfx}"
bucket="myvita-dr-test"
s3_key="dr-test-only-access"
s3_secret="dr-test-only-secret-${sfx}"
jwt="dr-test-only-not-a-real-secret-0123456789abcdef"

dump_service_logs() {
    local c
    for c in "$src_api" "$dst_api" "$src_db" "$dst_db" "$s3"; do
        docker inspect "$c" >/dev/null 2>&1 || continue
        echo "===== last log lines of ${c} ($(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null))" >&2
        docker logs --tail 60 "$c" >&2 2>&1 || true
    done
}
cleanup() {
    local rc=$?
    trap - EXIT INT TERM
    [ "$rc" = 0 ] || dump_service_logs
    docker rm -f "$s3" "$src_db" "$src_api" "$dst_db" "$dst_api" >/dev/null 2>&1 || true
    docker volume rm "$src_docs" "$dst_docs" >/dev/null 2>&1 || true
    docker network rm "$net" >/dev/null 2>&1 || true
    docker run --rm -v "${work}:/w" alpine:3 sh -c 'rm -rf /w/* /w/.[!.]*' >/dev/null 2>&1 || true
    rm -rf "$work"
    docker rmi "$backup_image" "$backend_image" >/dev/null 2>&1 || true
    exit "$rc"
}
trap cleanup EXIT INT TERM

# Bash 3.2 compatible (macOS): one result_<check> variable per check.
checks="postgres_backup documents_backup offsite_upload offsite_download postgres_restore documents_restore referential_integrity document_download orphan_detection"
for k in $checks; do printf -v "result_${k}" FAIL; done
pass() { printf -v "result_$1" PASS; }
report() {
    echo "=== Disaster recovery results"
    for k in $checks; do
        local var="result_${k}"
        printf '%-24s %s\n' "$k" "${!var}"
    done
}
step() { echo "--- $*"; }
die() { echo "FAIL: $*" >&2; report >&2; exit 1; }
expect_failure() {
    local label="$1"; shift
    if "$@" >"${work}/last.log" 2>&1; then cat "${work}/last.log" >&2; die "${label} unexpectedly succeeded"; fi
    echo "ok: ${label} failed as expected"
}
wait_for_db() {
    for _ in $(seq 1 60); do
        docker exec "$1" psql -h 127.0.0.1 -U myvita -d myvita -Atc 'select 1' >/dev/null 2>&1 && return 0
        sleep 1
    done
    die "database $1 did not start"
}
backend_env=(
    -e ENVIRONMENT=development -e COOKIE_SECURE=false -e "JWT_SECRET_KEY=${jwt}"
    -e ALLOW_PUBLIC_CLINIC_ONBOARDING=true -e ALLOW_PUBLIC_PATIENT_REGISTRATION=true
    -e ALLOW_DIRECT_STAFF_CREATION=true -e 'ALLOWED_HOSTS=["localhost","127.0.0.1"]'
)
start_api() { # name db documents_volume
    docker run -d --name "$1" --network "$net" -p 127.0.0.1::8000 "${backend_env[@]}" \
        -e "DATABASE_URL=postgresql+psycopg://myvita:${db_password}@$2:5432/myvita" \
        -v "$3:/var/lib/myvita/documents" "$backend_image" >/dev/null
    local port; port="$(docker port "$1" 8000/tcp | head -n1 | sed 's/.*://')"
    # Bounded wait (60 s) on the real readiness probe: /ready runs SELECT 1
    # against the database, /health only proves the process is up.
    for _ in $(seq 1 60); do
        [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" = true ] \
            || die "backend $1 exited during startup"
        curl -fsS "http://127.0.0.1:${port}/ready" >/dev/null 2>&1 && { echo "$port"; return 0; }
        sleep 1
    done
    die "backend $1 did not become ready (GET /ready) within 60 s"
}
# api <jar> <port> <method> <path> [curl args...] — sends the CSRF header from the jar.
# Prints the response body on 2xx. Otherwise names the request, prints the HTTP
# status and the (truncated) error body on stderr, and fails. Request bodies are
# never printed: they carry test passwords.
api() {
    local jar="$1" port="$2" method="$3" path="$4"; shift 4
    local csrf="" body code rc
    [ ! -f "$jar" ] || csrf="$(awk '$6 == "myvita_csrf" {print $7}' "$jar" | tail -n1)"
    body="$(mktemp "${work}/api-body.XXXXXX")"
    rc=0
    code="$(curl -sS -b "$jar" -c "$jar" -X "$method" -H "X-CSRF-Token: ${csrf}" -o "$body" -w '%{http_code}' \
        "http://127.0.0.1:${port}${path}" "$@")" || rc=$?
    if [ "$rc" != 0 ]; then
        echo "FAIL: ${method} ${path} on port ${port}: no HTTP response (curl exit ${rc})" >&2
        rm -f "$body"; return 1
    fi
    case "$code" in
        2??) cat "$body"; rm -f "$body"; return 0 ;;
    esac
    echo "FAIL: ${method} ${path} on port ${port} returned HTTP ${code}: $(head -c 500 "$body")" >&2
    rm -f "$body"; return 1
}
# json_field <name>: reads a JSON object on stdin; refuses empty or non-JSON input explicitly.
json_field() {
    python3 -c 'import json,sys
raw=sys.stdin.read()
if not raw.strip(): sys.exit("FAIL: expected a JSON response with field %r, got an empty body" % sys.argv[1])
try: data=json.loads(raw)
except ValueError: sys.exit("FAIL: expected JSON with field %r, got: %s" % (sys.argv[1], raw[:300]))
if not isinstance(data, dict) or sys.argv[1] not in data: sys.exit("FAIL: field %r missing from response: %s" % (sys.argv[1], raw[:300]))
print(data[sys.argv[1]])' "$1"
}
# RFC 6238 TOTP (SHA-1, 30 s, 6 digits) from a base32 secret; staff and clinic
# admins must enrol MFA before any clinical action.
totp() {
    python3 -c 'import base64,hmac,hashlib,struct,sys,time
s=sys.argv[1]; k=base64.b32decode(s.upper()+"="*(-len(s)%8))
h=hmac.new(k,struct.pack(">Q",int(time.time())//30),hashlib.sha1).digest(); o=h[-1]&15
print("%06d"%((struct.unpack(">I",h[o:o+4])[0]&0x7fffffff)%1000000))' "$1"
}
# enrol_mfa <jar> <port>: enrols TOTP on the session's user and prints the secret.
enrol_mfa() {
    local secret
    secret="$(api "$1" "$2" POST /api/v1/auth/mfa/setup | json_field secret)"
    api "$1" "$2" POST /api/v1/auth/mfa/enable -H 'Content-Type: application/json' \
        -d "{\"code\":\"$(totp "$secret")\"}" >/dev/null
    echo "$secret"
}
s3_env=(
    -e "OFFSITE_S3_BUCKET=${bucket}" -e OFFSITE_S3_PREFIX=myvita -e "OFFSITE_S3_ENDPOINT=http://${s3}:8333"
    -e OFFSITE_S3_REGION=us-east-1 -e "AWS_ACCESS_KEY_ID=${s3_key}" -e "AWS_SECRET_ACCESS_KEY=${s3_secret}"
)
in_backup() { # run a shipped script inside the shipped backup image
    local script="$1"; shift
    docker run --rm --network "$net" --entrypoint "/opt/myvita/${script}" "${s3_env[@]}" "${EXTRA_ENV[@]}" \
        -v "${work}/age.key:/run/myvita-age.key:ro" -e OFFSITE_AGE_IDENTITY_FILE=/run/myvita-age.key \
        -v "${work}/backups:/backups" "$backup_image" "$@"
}
EXTRA_ENV=(-e "DR_TEST=1")

step "Building images"
docker build -q -f "${repo_root}/backup/Dockerfile" -t "$backup_image" "$repo_root" >/dev/null
docker build -q -t "$backend_image" "${repo_root}/backend" >/dev/null
myvita_owner="$(docker run --rm --entrypoint sh "$backend_image" -c 'echo "$(id -u myvita):$(id -g myvita)"')"
# Test-only age key pair, generated inside the shipped image. Uploads only see
# the public key (as in production); downloads mount the private key.
docker run --rm --entrypoint age-keygen "$backup_image" > "${work}/age.key" 2>/dev/null
chmod 644 "${work}/age.key"
age_recipient="$(awk '/^# public key: /{print $4}' "${work}/age.key")"
[[ "$age_recipient" == age1* ]] || die "could not generate a test age key"
s3_env+=(-e "OFFSITE_AGE_RECIPIENT=${age_recipient}")

step "Starting isolated infrastructure (network ${net})"
docker network create "$net" >/dev/null
printf '{"identities":[{"name":"backup","credentials":[{"accessKey":"%s","secretKey":"%s"}],"actions":["Admin","Read","Write","List","Tagging"]}]}' \
    "$s3_key" "$s3_secret" > "${work}/s3.json"
chmod 644 "${work}/s3.json"
docker run -d --name "$s3" --network "$net" -v "${work}/s3.json:/etc/s3.json:ro" "$store_image" \
    server -ip="$s3" -ip.bind=0.0.0.0 -dir=/tmp -s3 -s3.port=8333 -s3.config=/etc/s3.json \
    -master.volumeSizeLimitMB=64 -volume.max=8 >/dev/null
docker run -d --name "$src_db" --network "$net" --tmpfs /var/lib/postgresql/data \
    -e POSTGRES_USER=myvita -e "POSTGRES_PASSWORD=${db_password}" -e POSTGRES_DB=myvita postgres:16-alpine >/dev/null
docker volume create "$src_docs" >/dev/null
mkdir -p "${work}/backups" "${work}/recovery"
wait_for_db "$src_db"
for _ in $(seq 1 90); do
    docker run --rm --network "$net" --entrypoint aws -e "AWS_ACCESS_KEY_ID=${s3_key}" -e "AWS_SECRET_ACCESS_KEY=${s3_secret}" \
        -e AWS_DEFAULT_REGION=us-east-1 "$backup_image" --endpoint-url "http://${s3}:8333" s3 mb "s3://${bucket}" >/dev/null 2>&1 && break
    sleep 2
done
docker run --rm --network "$net" --entrypoint aws -e "AWS_ACCESS_KEY_ID=${s3_key}" -e "AWS_SECRET_ACCESS_KEY=${s3_secret}" \
    -e AWS_DEFAULT_REGION=us-east-1 "$backup_image" --endpoint-url "http://${s3}:8333" s3api head-bucket --bucket "$bucket" \
    || die "object store did not start"

step "Migrating source and creating realistic data through the API"
docker run --rm --network "$net" "${backend_env[@]}" \
    -e "DATABASE_URL=postgresql+psycopg://myvita:${db_password}@${src_db}:5432/myvita" \
    "$backend_image" alembic upgrade head > "${work}/migrate.log" 2>&1 \
    || { cat "${work}/migrate.log" >&2; die "alembic upgrade head failed on the source database"; }
src_port="$(start_api "$src_api" "$src_db" "$src_docs")"
admin="${work}/admin.jar"; doctor="${work}/doctor.jar"; patient="${work}/patient.jar"
clinic_id="$(api "$admin" "$src_port" POST /api/v1/clinics -H 'Content-Type: application/json' \
    -d '{"clinic_name":"DR Clinic","admin_full_name":"DR Admin","admin_email":"admin@dr-recovery.example.pt","admin_password":"SenhaForte123!"}' | json_field id)"
enrol_mfa "$admin" "$src_port" >/dev/null
staff_id="$(api "$admin" "$src_port" POST /api/v1/staff -H 'Content-Type: application/json' \
    -d '{"full_name":"DR Doctor","email":"doctor@dr-recovery.example.pt","password":"SenhaForte123!","staff_role":"doctor"}' | json_field id)"
patient_id="$(api "$patient" "$src_port" POST /api/v1/patients/register -H 'Content-Type: application/json' \
    -d "{\"clinic_id\":\"${clinic_id}\",\"full_name\":\"DR Patient\",\"email\":\"patient@dr-recovery.example.pt\",\"password\":\"SenhaForte123!\"}" | json_field id)"
api "$admin" "$src_port" POST "/api/v1/patients/${patient_id}/care-team" -H 'Content-Type: application/json' \
    -d "{\"staff_id\":\"${staff_id}\"}" >/dev/null
# Staff created by an admin must change the temporary password and enrol MFA first.
api "$doctor" "$src_port" POST /api/v1/auth/login -H 'Content-Type: application/json' \
    -d '{"email":"doctor@dr-recovery.example.pt","password":"SenhaForte123!"}' >/dev/null
api "$doctor" "$src_port" POST /api/v1/auth/change-password -H 'Content-Type: application/json' \
    -d '{"current_password":"SenhaForte123!","new_password":"SenhaNova456!"}' >/dev/null
doctor_mfa_secret="$(enrol_mfa "$doctor" "$src_port")"
printf '%%PDF-1.7\nsynthetic disaster-recovery report %s\n' "$sfx" > "${work}/report.pdf"
printf '\x89PNG\r\n\x1a\n' > "${work}/scan.png"; head -c 50000 /dev/urandom >> "${work}/scan.png"
sha_list="${work}/original_sha.txt"; : > "$sha_list"
for f in report.pdf:application/pdf scan.png:image/png; do
    name="${f%%:*}"; mime="${f#*:}"
    id="$(api "$doctor" "$src_port" POST "/api/v1/patients/${patient_id}/documents" \
        -F "file=@${work}/${name};type=${mime};filename=${name}" -F "title=DR ${name}" | json_field id)"
    echo "${id} $(sha256sum "${work}/${name}" | awk '{print $1}')" >> "$sha_list"
done
conversation_id="$(api "$doctor" "$src_port" POST /api/v1/conversations -H 'Content-Type: application/json' \
    -d "{\"patient_id\":\"${patient_id}\"}" | json_field id)"
api "$doctor" "$src_port" POST "/api/v1/conversations/${conversation_id}/messages" -H 'Content-Type: application/json' \
    -d '{"body":"Synthetic DR message"}' >/dev/null
[ "$(wc -l < "$sha_list" | tr -d ' ')" = 2 ] || die "expected 2 uploaded documents"
echo "ok: clinic, doctor, patient, 2 documents, 1 conversation created"

step "Scheduled backup job: PostgreSQL + documents + off-site upload"
docker run --rm --network "$net" --entrypoint /opt/myvita/run_scheduled_backup.sh "${s3_env[@]}" \
    -e "DB_HOST=${src_db}" -e DB_PORT=5432 -e DB_NAME=myvita -e DB_USER=myvita -e "PGPASSWORD=${db_password}" \
    -e DOCUMENTS_BACKUP_ENABLED=true -e DOCUMENT_STORAGE_DIR=/documents -e OFFSITE_BACKUP_ENABLED=true \
    -e BACKUP_METRICS_DIR=/backups/metrics -e BACKUP_RETENTION_DAYS=7 \
    -v "${work}/backups:/backups" -v "${src_docs}:/documents:ro" "$backup_image" > "${work}/scheduled.log" 2>&1 \
    || { cat "${work}/scheduled.log" >&2; die "scheduled backup job failed"; }
grep -q 'Backup completed successfully' "${work}/scheduled.log" && pass postgres_backup
grep -q 'Documents backup completed successfully: .* files=2 ' "${work}/scheduled.log" && pass documents_backup
[ "$(grep -c 'Off-site upload completed successfully' "${work}/scheduled.log")" = 2 ] && pass offsite_upload
for secret in "$db_password" "$s3_secret" "synthetic disaster-recovery report"; do
    grep -q "$secret" "${work}/scheduled.log" && die "a secret or document content appeared in the backup log"
done
# The job runs as root and keeps /backups at 0700 (as in production); hand the
# tree to the CI user for the host-side reads below. Modes are left untouched.
docker run --rm -v "${work}/backups:/backups" alpine:3 chown -R "$(id -u):$(id -g)" /backups
metrics="$(cat "${work}/backups/metrics/myvita_backup.prom")"
for m in 'myvita_backup_last_run_success 1' 'myvita_documents_backup_last_run_success 1' \
         'myvita_documents_backup_last_file_count 2' 'myvita_offsite_backup_last_run_success 1'; do
    grep -q "^${m}$" <<< "$metrics" || die "metric missing: ${m}"
done
docker run --rm -v "${work}/backups:/backups" --entrypoint sh "$backup_image" \
    -c 'stat -c "%a %n" /backups/myvita_* ' | awk '$1 != "600" {print; bad=1} END {exit bad}' \
    || die "backup files must be 0600"
EXTRA_ENV=(-e DOCUMENTS_BACKUP_ENABLED=true)
in_backup check_backup.sh /backups | tail -n1 | tee "${work}/check.log"
EXTRA_ENV=(-e "DR_TEST=1")
grep -q 'BACKUP_STATUS postgres=OK documents=OK' "${work}/check.log" || die "check_backup.sh did not report both backups OK"
docker run --rm --network "$net" --entrypoint aws "${s3_env[@]}" -e AWS_DEFAULT_REGION=us-east-1 "$backup_image" \
    --endpoint-url "http://${s3}:8333" s3api list-objects-v2 --bucket "$bucket" --prefix myvita/ --query 'Contents[].Key' --output text \
    | tr '\t' '\n' | sort | tee "${work}/objects.txt"
grep -qE '^myvita/postgres/myvita_[0-9]{8}T[0-9]{6}Z\.dump\.age\.sha256$' "${work}/objects.txt" || die "postgres objects missing"
grep -qE '^myvita/documents/myvita_documents_[0-9]{8}T[0-9]{6}Z\.tar\.gz\.age\.sha256$' "${work}/objects.txt" || die "documents objects missing"
grep -qvE '\.(dump|tar\.gz)\.age(\.sha256)?$' "${work}/objects.txt" && die "unexpected (unencrypted?) objects were uploaded"
first_object="$(grep -E '\.dump\.age$' "${work}/objects.txt" | head -n1)"
docker run --rm --network "$net" --entrypoint sh "${s3_env[@]}" -e AWS_DEFAULT_REGION=us-east-1 "$backup_image" -c \
    "aws --endpoint-url \$OFFSITE_S3_ENDPOINT s3 cp s3://${bucket}/${first_object} - | head -c 21" > "${work}/header.txt"
[ "$(cat "${work}/header.txt")" = "age-encryption.org/v1" ] || die "off-site dump is not age-encrypted"

step "Off-site failure cases"
dump_name="$(basename "$(find "${work}/backups" -maxdepth 1 -name 'myvita_[0-9]*.dump' | head -n1)")"
expect_failure "upload with invalid credentials" docker run --rm --network "$net" --entrypoint /opt/myvita/upload_offsite_backup.sh \
    "${s3_env[@]}" -e AWS_SECRET_ACCESS_KEY=wrong-secret -v "${work}/backups:/backups" "$backup_image" "/backups/${dump_name}"
grep -q 'off-site upload failed' "${work}/last.log" || die "invalid credentials did not fail at upload"
grep -q "$s3_secret" "${work}/last.log" && die "credentials appeared in the failure log"
expect_failure "download of a missing object" in_backup download_offsite_backup.sh myvita/postgres/myvita_20000101T000000Z.dump /backups/missing-check
printf 'tampered' > "${work}/tampered.dump"
docker run --rm --network "$net" --entrypoint sh "${s3_env[@]}" -v "${work}:/w" "$backup_image" -c \
    "aws --endpoint-url \$OFFSITE_S3_ENDPOINT s3 cp /w/tampered.dump s3://${bucket}/myvita/postgres/myvita_20000101T000000Z.dump --only-show-errors && \
     aws --endpoint-url \$OFFSITE_S3_ENDPOINT s3 cp /w/backups/${dump_name}.sha256 s3://${bucket}/myvita/postgres/myvita_20000101T000000Z.dump.sha256 --only-show-errors && \
     aws --endpoint-url \$OFFSITE_S3_ENDPOINT s3 cp /w/tampered.dump s3://${bucket}/other-app/myvita_20000101T000000Z.dump --only-show-errors"
expect_failure "download of a tampered object" in_backup download_offsite_backup.sh myvita/postgres/myvita_20000101T000000Z.dump /backups/tamper-check
grep -q 'checksum does not match' "${work}/last.log" || die "tampered object not detected by checksum"
[ -z "$(find "${work}/backups/tamper-check" -name 'myvita_*' 2>/dev/null)" ] || die "a tampered download was published"
in_backup prune_offsite_backups.sh | tee "${work}/prune.log"
grep -q 'removed=1 ' "${work}/prune.log" || die "off-site retention did not remove the expired object"
docker run --rm --network "$net" --entrypoint aws "${s3_env[@]}" -e AWS_DEFAULT_REGION=us-east-1 "$backup_image" \
    --endpoint-url "http://${s3}:8333" s3api list-objects-v2 --bucket "$bucket" --query 'Contents[].Key' --output text \
    | tr '\t' '\n' > "${work}/after-prune.txt"
grep -q '^other-app/myvita_20000101T000000Z.dump$' "${work}/after-prune.txt" || die "retention deleted outside the prefix"
grep -q "^myvita/postgres/${dump_name}.age$" "${work}/after-prune.txt" || die "retention deleted the newest backup"
in_backup check_offsite_bucket.sh > "${work}/bucket.log" 2>&1 || true
grep -q 'OFFSITE_BUCKET bucket=myvita-dr-test versioning=' "${work}/bucket.log" || die "bucket protection report missing"
grep -q 'versioning=Enabled' "${work}/bucket.log" && die "test bucket must not be reported as versioned"
cat "${work}/bucket.log"

expect_failure "encrypted download without the private key" docker run --rm --network "$net" \
    --entrypoint /opt/myvita/download_offsite_backup.sh "${s3_env[@]}" -v "${work}/backups:/backups" "$backup_image" \
    "myvita/postgres/${dump_name}.age" /backups/nokey-check
grep -q 'OFFSITE_AGE_IDENTITY_FILE' "${work}/last.log" || die "missing key was not reported"

step "DISASTER: destroying the source database, documents volume and local backups"
docker rm -f "$src_api" "$src_db" >/dev/null
docker volume rm "$src_docs" >/dev/null
docker run --rm -v "${work}/backups:/backups" alpine:3 sh -c 'rm -rf /backups/* /backups/.[!.]*'
[ -z "$(ls -A "${work}/backups")" ] || die "local backups still present"

step "Recovery: downloading the latest backup set from off-site storage"
in_backup download_offsite_backup.sh --latest /backups/recovery | tee "${work}/download.log"
[ "$(grep -c 'Off-site download verified' "${work}/download.log")" = 2 ] && pass offsite_download
docker run --rm -v "${work}/backups:/backups" alpine:3 chown -R "$(id -u):$(id -g)" /backups
dump="$(find "${work}/backups/recovery" -name 'myvita_[0-9]*.dump')"
archive="$(find "${work}/backups/recovery" -name 'myvita_documents_*.tar.gz')"
[ -s "$dump" ] && [ -s "$archive" ] || die "recovery set incomplete"

step "Isolated verification of the recovered backup set"
mkdir -p "${work}/verify-metrics"
BACKUP_METRICS_DIR="${work}/verify-metrics" "${repo_root}/scripts/verify_restore.sh" "$dump" \
    --alembic-image "$backend_image" --documents "$archive" | tee "${work}/verify.log"
grep -q '^POSTGRES_RESTORE=OK DOCUMENTS_RESTORE=OK REFERENTIAL_INTEGRITY=OK$' "${work}/verify.log" \
    || die "verify_restore.sh did not report a complete recovery"
grep -q 'missing_files=0 orphan_files=0' "${work}/verify.log" || die "unexpected document discrepancies"
grep -q '^myvita_recovery_verification_last_run_success 1$' "${work}/verify-metrics/myvita_backup.prom" \
    || die "recovery verification metric not recorded"

step "Real restore into a fresh database and a fresh documents volume"
docker run -d --name "$dst_db" --network "$net" --tmpfs /var/lib/postgresql/data \
    -e POSTGRES_USER=myvita -e "POSTGRES_PASSWORD=${db_password}" -e POSTGRES_DB=myvita postgres:16-alpine >/dev/null
wait_for_db "$dst_db"
db_env=(-e "DB_HOST=${dst_db}" -e DB_PORT=5432 -e DB_NAME=myvita -e DB_USER=myvita -e "PGPASSWORD=${db_password}")
EXTRA_ENV=("${db_env[@]}")
in_backup restore_db.sh "/backups/recovery/$(basename "$dump")" --yes > "${work}/restore-db.log" 2>&1 \
    || { cat "${work}/restore-db.log" >&2; die "restore_db.sh failed"; }
EXTRA_ENV=(-e "DR_TEST=1")
pass postgres_restore
docker volume create "$dst_docs" >/dev/null
docker run --rm --network "$net" --entrypoint /opt/myvita/restore_documents.sh -v "${work}/backups:/backups" \
    -v "${dst_docs}:/restore" "$backup_image" "/backups/recovery/$(basename "$archive")" /restore --owner "$myvita_owner" \
    | tee "${work}/restore-docs.log"
grep -q 'Documents restore completed: target=/restore files=2 ' "${work}/restore-docs.log" && pass documents_restore
expect_failure "second restore over the populated volume" docker run --rm --entrypoint /opt/myvita/restore_documents.sh \
    -v "${work}/backups:/backups" -v "${dst_docs}:/restore" "$backup_image" "/backups/recovery/$(basename "$archive")" /restore
docker run --rm --network "$net" --entrypoint /opt/myvita/verify_documents_storage.sh "${db_env[@]}" \
    -v "${dst_docs}:/restore:ro" "$backup_image" /restore | tee "${work}/consistency.log"
grep -q 'records=2 stored_files=2 missing_files=0 orphan_files=0' "${work}/consistency.log" && pass referential_integrity
docker run --rm -v "${dst_docs}:/restore" alpine:3 sh -c 'stat -c "%a %u:%g" /restore /restore/*' | tee "${work}/perms.txt"
awk -v owner="$myvita_owner" 'NR == 1 && ($1 != "700" || $2 != owner) {bad=1} NR > 1 && ($1 != "600" || $2 != owner) {bad=1} END {exit bad}' \
    "${work}/perms.txt" || die "restored documents have the wrong permissions/owner"

step "Application reads on the recovered system"
dst_port="$(start_api "$dst_api" "$dst_db" "$dst_docs")"
rdoctor="${work}/rdoctor.jar"; rpatient="${work}/rpatient.jar"
api "$rdoctor" "$dst_port" POST /api/v1/auth/login -H 'Content-Type: application/json' \
    -d '{"email":"doctor@dr-recovery.example.pt","password":"SenhaNova456!"}' >/dev/null || die "doctor cannot log in after recovery"
# The MFA enrolment (encrypted seed) must survive the recovery too.
api "$rdoctor" "$dst_port" POST /api/v1/auth/mfa/verify -H 'Content-Type: application/json' \
    -d "{\"code\":\"$(totp "$doctor_mfa_secret")\"}" >/dev/null || die "doctor MFA does not verify after recovery"
listed="$(api "$rdoctor" "$dst_port" GET "/api/v1/patients/${patient_id}/documents" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')"
[ "$listed" = 2 ] || die "expected 2 documents after recovery, got ${listed}"
downloads_ok=0
while read -r id expected_sha; do
    api "$rdoctor" "$dst_port" GET "/api/v1/documents/${id}/download" > "${work}/dl-${id}" || die "download of ${id} failed"
    [ "$(sha256sum "${work}/dl-${id}" | awk '{print $1}')" = "$expected_sha" ] || die "downloaded document ${id} differs"
    downloads_ok=$((downloads_ok + 1))
done < "$sha_list"
[ "$downloads_ok" = 2 ] && pass document_download
api "$rpatient" "$dst_port" POST /api/v1/auth/login -H 'Content-Type: application/json' \
    -d '{"email":"patient@dr-recovery.example.pt","password":"SenhaForte123!"}' >/dev/null
[ "$(api "$rpatient" "$dst_port" GET /api/v1/conversations | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["unread_count"])')" = 1 ] \
    || die "patient conversation not recovered"
[ "$(api "$rpatient" "$dst_port" GET /api/v1/notifications/unread-count | json_field count)" -ge 1 ] \
    || die "patient notifications not recovered"
echo "ok: login, document list, byte-identical downloads, conversation and notifications after recovery"

step "Orphan / missing-file detection on the recovered storage"
victim="$(docker run --rm -v "${dst_docs}:/restore" alpine:3 sh -c 'ls /restore | head -n1')"
docker run --rm -v "${dst_docs}:/restore" alpine:3 sh -c "mv /restore/${victim} /tmp/ && printf stray > /restore/00000000000000000000000000000000"
expect_failure "consistency check with a missing and an orphan file" docker run --rm --network "$net" \
    --entrypoint /opt/myvita/verify_documents_storage.sh "${db_env[@]}" -v "${dst_docs}:/restore:ro" "$backup_image" /restore
grep -q "missing_file storage_key=${victim}" "${work}/last.log" || die "missing file not reported"
grep -q 'orphan_file storage_key=00000000000000000000000000000000' "${work}/last.log" || die "orphan file not reported"
grep -q 'missing_files=1 orphan_files=1' "${work}/last.log" && pass orphan_detection
[ "$(docker run --rm -v "${dst_docs}:/restore" alpine:3 sh -c 'ls /restore | wc -l' | tr -d ' ')" = 2 ] \
    || die "the consistency check modified storage"

report
for k in $checks; do var="result_${k}"; [ "${!var}" = PASS ] || die "${k} did not pass"; done
echo "Off-site disaster recovery integration test passed."
