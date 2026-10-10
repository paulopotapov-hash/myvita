#!/usr/bin/env bash
#
# Proves a backup is actually recoverable: restores it into a throwaway
# PostgreSQL container and checks schema, constraints and data integrity.
# A dump is not considered valid just because pg_dump or `pg_restore --list`
# succeeded — this script is the stronger check.
#
# Isolation: the temporary server runs in its own container on its own
# Docker network, with no published ports and its data on tmpfs. It never
# connects to the development or production database, and everything it
# creates is removed on exit (success or failure).
#
# Usage:
#   ./scripts/verify_restore.sh <dump_file> [--alembic-image IMAGE] [--documents ARCHIVE]
#
#   --alembic-image IMAGE  Backend image (e.g. one built from ./backend). After
#                          restoring, runs `alembic upgrade head` and
#                          `alembic check` against the restored copy, so an
#                          older dump is brought to the current schema and
#                          schema/model drift is detected.
#   --documents ARCHIVE    myvita_documents_<ts>.tar.gz from the same backup set.
#                          It is restored (scripts/restore_documents.sh) into a
#                          private temp directory and every `documents` row must
#                          have its file (missing_files=0). Orphan files are
#                          reported; they fail the check unless
#                          VERIFY_ALLOW_ORPHAN_FILES=true (expected when uploads
#                          happened between the dump and the archive).
#
# Optional environment:
#   VERIFY_POSTGRES_IMAGE      default postgres:16-alpine (match production)
#   EXPECTED_ALEMBIC_REVISION  fail unless the restored revision equals this
#   VERIFY_READY_TIMEOUT       seconds to wait for the temp server (default 60)
#   BACKUP_METRICS_DIR         if set, records recovery-success/-failure there
#                              (write_backup_metrics.sh) for monitoring
#
# Requires: docker, sha256sum (or shasum). Exit code 0 only on full success.
#
set -euo pipefail
umask 077

# The current myVita schema (alembic head). scripts/test_restore_verification.sh
# compares this list with a freshly migrated database, so it cannot silently go stale.
# clinical_* (except clinical_care_assignments) and deprecated_notification_targets
# are deprecated after the main/messages-backend merge but still exist and may
# hold data, so a restore must bring them back too.
EXPECTED_TABLES=(
    alembic_version appointment_requests appointments audit_logs clinical_care_assignments
    clinical_conversations clinical_document_versions clinical_documents clinical_messages
    clinics consents conversations deprecated_notification_targets documents invitations
    medical_record_revisions medical_records medications messages mfa_recovery_codes
    notifications password_reset_tokens patients staff user_mfa users
)
# Constraints/indexes that encode tenant isolation or core access paths.
# Constraints are <table>.<name>: names are only unique per table (the deprecated
# clinical_documents reuses fk_documents_patient_clinic).
EXPECTED_CONSTRAINTS=(
    patients.uq_patients_id_clinic patients.uq_patients_user_id staff.uq_staff_user_id
    medications.fk_medications_patient_clinic conversations.fk_conversations_patient_clinic
    documents.fk_documents_patient_clinic conversations.uq_conversations_patient_staff
)
EXPECTED_INDEXES=(
    ix_users_email ix_appointments_clinic_scheduled_at ix_notifications_user_created
    ix_messages_conversation_created ix_documents_patient_created ix_audit_logs_resource
)

dump_file=""
alembic_image=""
documents_archive=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --alembic-image) alembic_image="${2:?--alembic-image needs a value}"; shift 2 ;;
        --documents) documents_archive="${2:?--documents needs a value}"; shift 2 ;;
        -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
        -*) echo "ERROR: unknown option: $1" >&2; exit 2 ;;
        *) [ -z "$dump_file" ] || { echo "ERROR: only one dump file may be given" >&2; exit 2; }; dump_file="$1"; shift ;;
    esac
done

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }
record_metric() {
    [ -z "${BACKUP_METRICS_DIR:-}" ] || "${script_dir}/write_backup_metrics.sh" "$1" >/dev/null 2>&1 || true
}
postgres_state=FAILED
documents_state=SKIPPED
integrity_state=FAILED
fail() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ERROR: $*" >&2
    echo "POSTGRES_RESTORE=${postgres_state} DOCUMENTS_RESTORE=${documents_state} REFERENTIAL_INTEGRITY=${integrity_state}" >&2
    echo "RESTORE_VERIFY result=FAILURE file=$(basename "${dump_file:-none}") reason=\"$*\"" >&2
    record_metric recovery-failure
    exit 1
}

[ -n "$dump_file" ] || { echo "Usage: $0 <dump_file> [--alembic-image IMAGE]" >&2; exit 2; }
[ -f "$dump_file" ] || fail "dump file not found: $dump_file"
[ -s "$dump_file" ] || fail "dump file is empty: $dump_file"
command -v docker >/dev/null || fail "docker is required"
dump_file="$(cd "$(dirname "$dump_file")" && pwd)/$(basename "$dump_file")"
if [ -n "$documents_archive" ]; then
    [ -s "$documents_archive" ] || fail "documents archive not found or empty: $documents_archive"
    documents_state=FAILED
fi

postgres_image="${VERIFY_POSTGRES_IMAGE:-postgres:16-alpine}"
ready_timeout="${VERIFY_READY_TIMEOUT:-60}"
started_at="$(date +%s)"
suffix="$(od -An -N6 -tx1 /dev/urandom | tr -d ' \n')"
container="myvita-restore-verify-${suffix}"
network="myvita-restore-verify-${suffix}"
db_name="myvita_restore_verify"
# Only ever used inside the throwaway network; never printed.
db_password="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"

documents_dir=""
cleanup() {
    docker rm -f "$container" >/dev/null 2>&1 || true
    docker network rm "$network" >/dev/null 2>&1 || true
    [ -z "$documents_dir" ] || rm -rf "$documents_dir"
}
trap cleanup EXIT INT TERM

log "Restore verification started: file=$(basename "$dump_file") postgres_image=${postgres_image}"

checksum_file="${dump_file}.sha256"
if [ -f "$checksum_file" ]; then
    if command -v sha256sum >/dev/null; then
        (cd "$(dirname "$dump_file")" && sha256sum -c "$(basename "$checksum_file")" >/dev/null) \
            || fail "checksum mismatch for $(basename "$dump_file")"
    else
        (cd "$(dirname "$dump_file")" && shasum -a 256 -c "$(basename "$checksum_file")" >/dev/null) \
            || fail "checksum mismatch for $(basename "$dump_file")"
    fi
    log "Checksum OK"
else
    log "WARNING: no .sha256 sidecar found; continuing with archive and restore checks only"
fi

docker network create --internal --label myvita.restore-verify=true "$network" >/dev/null \
    || fail "could not create isolated docker network"
docker run -d --name "$container" --network "$network" --label myvita.restore-verify=true \
    --tmpfs /var/lib/postgresql/data:rw,size=2g \
    -e POSTGRES_PASSWORD="$db_password" -e POSTGRES_DB="$db_name" \
    "$postgres_image" >/dev/null || fail "could not start temporary PostgreSQL ($postgres_image)"

# The official image restarts once during initialisation; wait for the final server.
deadline=$(( $(date +%s) + ready_timeout ))
until docker exec "$container" pg_isready -U postgres -d "$db_name" -h 127.0.0.1 >/dev/null 2>&1 \
    && docker exec -u postgres "$container" psql -h 127.0.0.1 -d "$db_name" -Atc 'select 1' >/dev/null 2>&1; do
    [ "$(date +%s)" -lt "$deadline" ] || fail "temporary PostgreSQL did not become ready within ${ready_timeout}s"
    sleep 1
done
log "Temporary PostgreSQL ready: container=${container} (isolated network, no published ports)"

psql_q() { docker exec -u postgres "$container" psql -X -v ON_ERROR_STOP=1 -d "$db_name" -Atc "$1"; }

docker cp "$dump_file" "${container}:/tmp/restore.dump" >/dev/null || fail "could not copy dump into temporary server"
docker exec "$container" chown postgres /tmp/restore.dump
docker exec -u postgres "$container" pg_restore --list /tmp/restore.dump >/dev/null \
    || fail "archive is unreadable (pg_restore --list failed)"

# --no-owner/--no-privileges: the production role does not exist in the temp
# server. -1: a partial restore is a failed restore.
if ! docker exec -u postgres "$container" pg_restore --no-owner --no-privileges --exit-on-error -1 \
        -d "$db_name" /tmp/restore.dump; then
    fail "pg_restore failed"
fi
log "pg_restore completed"

if [ -n "$alembic_image" ]; then
    log "Running alembic upgrade head + alembic check with ${alembic_image}"
    alembic_env=(
        -e "DATABASE_URL=postgresql+psycopg://postgres:${db_password}@${container}:5432/${db_name}"
        -e ENVIRONMENT=development -e COOKIE_SECURE=false
        -e JWT_SECRET_KEY=restore-verification-only-not-a-real-secret-0123456789
    )
    docker run --rm --network "$network" "${alembic_env[@]}" "$alembic_image" alembic upgrade head >/dev/null \
        || fail "alembic upgrade head failed on the restored database"
    docker run --rm --network "$network" "${alembic_env[@]}" "$alembic_image" alembic check >/dev/null \
        || fail "alembic check found schema drift on the restored database"
    log "Alembic upgrade/check OK"
fi

psql_q 'select 1' >/dev/null || fail "restored database does not accept queries"

revision="$(psql_q "select string_agg(version_num, ',') from alembic_version" 2>/dev/null || true)"
[ -n "$revision" ] || fail "alembic_version is missing or empty"
if [ -n "${EXPECTED_ALEMBIC_REVISION:-}" ] && [ "$revision" != "$EXPECTED_ALEMBIC_REVISION" ]; then
    fail "alembic revision ${revision} != expected ${EXPECTED_ALEMBIC_REVISION}"
fi

missing=()
for table in "${EXPECTED_TABLES[@]}"; do
    [ "$(psql_q "select to_regclass('public.${table}') is not null")" = "t" ] || missing+=("$table")
done
if [ "${#missing[@]}" -gt 0 ]; then
    hint=""
    [ -n "$alembic_image" ] || hint=" (an older dump may need --alembic-image to reach the current schema)"
    fail "missing tables: ${missing[*]}${hint}"
fi

for constraint in "${EXPECTED_CONSTRAINTS[@]}"; do
    table="${constraint%%.*}"; name="${constraint#*.}"
    [ "$(psql_q "select count(*) from pg_constraint where conrelid = to_regclass('public.${table}') and conname = '${name}' and convalidated")" = "1" ] \
        || fail "missing or unvalidated constraint: ${constraint}"
done
for index in "${EXPECTED_INDEXES[@]}"; do
    [ "$(psql_q "select to_regclass('public.${index}') is not null")" = "t" ] || fail "missing index: ${index}"
done
fk_count="$(psql_q "select count(*) from pg_constraint c join pg_namespace n on n.oid = c.connamespace where n.nspname = 'public' and c.contype = 'f'")"
[ "$fk_count" -ge 20 ] || fail "only ${fk_count} foreign keys restored; schema looks incomplete"
invalid_fk="$(psql_q "select count(*) from pg_constraint where contype = 'f' and not convalidated")"
[ "$invalid_fk" = "0" ] || fail "${invalid_fk} foreign keys are not validated"

counts=""
total_rows=0
for table in "${EXPECTED_TABLES[@]}"; do
    n="$(psql_q "select count(*) from public.${table}")" || fail "row count failed for ${table}"
    counts+=" ${table}=${n}"
    total_rows=$((total_rows + n))
done
log "Row counts:${counts}"

# Representative application read paths and tenant invariants. Each query
# must run, and each invariant count must be zero.
psql_q "select count(*) from appointments a join patients p on p.id = a.patient_id join users u on u.id = p.user_id join staff s on s.id = a.staff_id" >/dev/null \
    || fail "appointment read path failed"
psql_q "select count(*) from conversations c join messages m on m.conversation_id = c.id" >/dev/null \
    || fail "conversation/message read path failed"
psql_q "select count(*) from documents d join patients p on p.id = d.patient_id" >/dev/null \
    || fail "document read path failed"
psql_q "select count(*) from notifications n join users u on u.id = n.user_id" >/dev/null \
    || fail "notification read path failed"

check_zero() {
    local label="$1" sql="$2" n
    n="$(psql_q "$sql")" || fail "integrity query failed: ${label}"
    [ "$n" = "0" ] || fail "integrity violation: ${label} (${n} rows)"
}
check_zero "appointment clinic differs from patient clinic" \
    "select count(*) from appointments a join patients p on p.id = a.patient_id where a.clinic_id <> p.clinic_id"
check_zero "appointment clinic differs from staff clinic" \
    "select count(*) from appointments a join staff s on s.id = a.staff_id where a.clinic_id <> s.clinic_id"
check_zero "conversation clinic differs from staff clinic" \
    "select count(*) from conversations c join staff s on s.id = c.staff_id where c.clinic_id <> s.clinic_id"
check_zero "message clinic differs from conversation clinic" \
    "select count(*) from messages m join conversations c on c.id = m.conversation_id where m.clinic_id <> c.clinic_id"
check_zero "notification clinic differs from recipient clinic" \
    "select count(*) from notifications n join users u on u.id = n.user_id where u.clinic_id is not null and n.clinic_id <> u.clinic_id"
check_zero "patient profile in a different clinic from its user" \
    "select count(*) from patients p join users u on u.id = p.user_id where u.clinic_id is distinct from p.clinic_id"
check_zero "staff profile in a different clinic from its user" \
    "select count(*) from staff s join users u on u.id = s.user_id where u.clinic_id is distinct from s.clinic_id"
log "Integrity checks OK"
postgres_state=OK

documents_summary=""
if [ -n "$documents_archive" ]; then
    documents_dir="$(mktemp -d)"
    chmod 700 "$documents_dir"
    "${script_dir}/restore_documents.sh" "$documents_archive" "$documents_dir" --owner "$(id -u):$(id -g)" >/dev/null \
        || fail "documents archive could not be restored"
    documents_state=OK
    psql_q "select storage_key from documents order by 1" | LC_ALL=C sort > "${documents_dir}/.db_keys" \
        || fail "could not read document records"
    find "$documents_dir" -maxdepth 1 -type f ! -name '.*' -exec basename {} \; | LC_ALL=C sort > "${documents_dir}/.file_keys"
    missing_files="$(LC_ALL=C comm -23 "${documents_dir}/.db_keys" "${documents_dir}/.file_keys" | wc -l | tr -d ' ')"
    orphan_files="$(LC_ALL=C comm -13 "${documents_dir}/.db_keys" "${documents_dir}/.file_keys" | wc -l | tr -d ' ')"
    LC_ALL=C comm -23 "${documents_dir}/.db_keys" "${documents_dir}/.file_keys" | sed 's/^/missing_file storage_key=/'
    LC_ALL=C comm -13 "${documents_dir}/.db_keys" "${documents_dir}/.file_keys" | sed 's/^/orphan_file storage_key=/'
    documents_summary=" documents=$(wc -l < "${documents_dir}/.file_keys" | tr -d ' ') missing_files=${missing_files} orphan_files=${orphan_files}"
    log "Documents: records=$(wc -l < "${documents_dir}/.db_keys" | tr -d ' ')${documents_summary}"
    [ "$missing_files" = "0" ] || fail "${missing_files} document records have no restored file"
    if [ "$orphan_files" != "0" ] && [ "${VERIFY_ALLOW_ORPHAN_FILES:-false}" != "true" ]; then
        fail "${orphan_files} restored files have no document record"
    fi
fi
integrity_state=OK

duration="$(( $(date +%s) - started_at ))"
record_metric recovery-success
echo "POSTGRES_RESTORE=${postgres_state} DOCUMENTS_RESTORE=${documents_state} REFERENTIAL_INTEGRITY=${integrity_state}"
echo "RESTORE_VERIFY result=SUCCESS file=$(basename "$dump_file") revision=${revision} tables=${#EXPECTED_TABLES[@]} foreign_keys=${fk_count} total_rows=${total_rows}${documents_summary} alembic_check=$([ -n "$alembic_image" ] && echo yes || echo skipped) duration_seconds=${duration}"
