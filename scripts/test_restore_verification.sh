#!/usr/bin/env bash
#
# End-to-end backup/restore test against REAL PostgreSQL servers in throwaway
# containers. Complements test_backup_scripts.sh (which fakes pg_dump to test
# script logic) by proving the actual recovery path:
#
#   migrate + seed source DB -> backup_db.sh -> verify_restore.sh (+ alembic check)
#   -> corrupted/invalid backups rejected -> restore_db.sh safety guards
#   -> real connection failures fail the backup
#
# Everything runs on a private Docker network with tmpfs data and no published
# ports; the developer's database and volumes are never touched. Requires docker.
#
# Usage: ./scripts/test_restore_verification.sh   (from any directory)
#
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
suffix="$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
network="myvita-restore-test-${suffix}"
source_db="myvita-restore-test-src-${suffix}"
backup_image="myvita-backup:restore-test-${suffix}"
backend_image="myvita-backend:restore-test-${suffix}"
work_dir="$(mktemp -d)"
password="restore-test-only-${suffix}"

cleanup() {
    docker rm -f "$source_db" >/dev/null 2>&1 || true
    docker network rm "$network" >/dev/null 2>&1 || true
    docker rmi "$backup_image" "$backend_image" >/dev/null 2>&1 || true
    # Files written by containers may be root-owned; remove them from a container.
    docker run --rm -v "${work_dir}:/w" alpine:3 sh -c 'rm -rf /w/* /w/.[!.]*' >/dev/null 2>&1 || true
    rm -rf "$work_dir"
}
trap cleanup EXIT INT TERM

step() { echo "--- $*"; }
expect_failure() {
    local label="$1"; shift
    if "$@" >"${work_dir}/last.log" 2>&1; then
        echo "FAIL: ${label} unexpectedly succeeded" >&2; cat "${work_dir}/last.log" >&2; exit 1
    fi
    echo "ok: ${label} failed as expected"
}
# Runs a command (including shell functions) with extra variables set, in a subshell.
in_env() {
    local vars=()
    while [[ "${1:-}" == *=* ]]; do vars+=("$1"); shift; done
    ( export "${vars[@]}"; "$@" )
}
count_dumps() { find "${work_dir}/backups" -maxdepth 1 -name 'myvita_*.dump' -type f 2>/dev/null | wc -l | tr -d ' '; }

step "Building images"
docker build -q -f "${repo_root}/backup/Dockerfile" -t "$backup_image" "$repo_root" >/dev/null
docker build -q -t "$backend_image" "${repo_root}/backend" >/dev/null

step "Starting isolated source PostgreSQL"
docker network create --internal "$network" >/dev/null
docker run -d --name "$source_db" --network "$network" --tmpfs /var/lib/postgresql/data \
    -e POSTGRES_USER=myvita -e POSTGRES_PASSWORD="$password" -e POSTGRES_DB=myvita \
    postgres:16-alpine >/dev/null
for _ in $(seq 1 60); do
    docker exec "$source_db" pg_isready -h 127.0.0.1 -U myvita -d myvita >/dev/null 2>&1 \
        && docker exec "$source_db" psql -h 127.0.0.1 -U myvita -d myvita -Atc 'select 1' >/dev/null 2>&1 && break
    sleep 1
done
src_sql() { docker exec -i "$source_db" psql -X -v ON_ERROR_STOP=1 -U myvita -d myvita -Atq "$@"; }

step "Migrating source to head"
docker run --rm --network "$network" \
    -e "DATABASE_URL=postgresql+psycopg://myvita:${password}@${source_db}:5432/myvita" \
    -e ENVIRONMENT=development -e COOKIE_SECURE=false \
    -e JWT_SECRET_KEY=restore-test-only-not-a-real-secret-0123456789 \
    "$backend_image" alembic upgrade head >/dev/null
head_revision="$(src_sql -c 'select version_num from alembic_version')"

step "Checking verify_restore.sh EXPECTED_TABLES matches the migrated schema"
expected="$(sed -n '/^EXPECTED_TABLES=(/,/^)/p' "${repo_root}/scripts/verify_restore.sh" | sed '1d;$d' | tr -s ' \n' '\n' | sed '/^$/d' | sort)"
actual="$(src_sql -c "select table_name from information_schema.tables where table_schema = 'public' order by 1")"
if [ "$expected" != "$actual" ]; then
    echo "FAIL: EXPECTED_TABLES in verify_restore.sh is stale" >&2
    diff <(echo "$expected") <(echo "$actual") >&2 || true
    exit 1
fi
echo "ok: table list matches (${head_revision})"

step "Seeding representative data across all domains"
src_sql <<'SQL'
insert into clinics (id, name) values ('11111111-0000-0000-0000-000000000001', 'Clinica Restore');
insert into users (id, email, hashed_password, full_name, role, clinic_id, is_active, token_epoch) values
  ('22222222-0000-0000-0000-000000000001', 'doctor@restore.test', 'x', 'Doctor', 'staff', '11111111-0000-0000-0000-000000000001', true, 0),
  ('22222222-0000-0000-0000-000000000002', 'patient@restore.test', 'x', 'Patient', 'patient', '11111111-0000-0000-0000-000000000001', true, 0);
insert into staff (id, user_id, clinic_id, staff_role) values
  ('33333333-0000-0000-0000-000000000001', '22222222-0000-0000-0000-000000000001', '11111111-0000-0000-0000-000000000001', 'doctor');
insert into patients (id, user_id, clinic_id) values
  ('44444444-0000-0000-0000-000000000001', '22222222-0000-0000-0000-000000000002', '11111111-0000-0000-0000-000000000001');
insert into appointments (id, clinic_id, patient_id, staff_id, scheduled_at, duration_minutes, status) values
  ('55555555-0000-0000-0000-000000000001', '11111111-0000-0000-0000-000000000001', '44444444-0000-0000-0000-000000000001',
   '33333333-0000-0000-0000-000000000001', now() + interval '1 day', 30, 'scheduled');
insert into conversations (id, clinic_id, patient_id, staff_id) values
  ('66666666-0000-0000-0000-000000000001', '11111111-0000-0000-0000-000000000001', '44444444-0000-0000-0000-000000000001',
   '33333333-0000-0000-0000-000000000001');
insert into messages (id, conversation_id, clinic_id, sender_user_id, body) values
  ('77777777-0000-0000-0000-000000000001', '66666666-0000-0000-0000-000000000001', '11111111-0000-0000-0000-000000000001',
   '22222222-0000-0000-0000-000000000001', 'synthetic restore-test message');
insert into notifications (id, clinic_id, user_id, title, message, is_read) values
  ('88888888-0000-0000-0000-000000000001', '11111111-0000-0000-0000-000000000001', '22222222-0000-0000-0000-000000000002',
   'Nova mensagem', 'synthetic', false);
insert into documents (id, clinic_id, patient_id, uploaded_by_user_id, original_filename, storage_key, content_type, file_size) values
  ('99999999-0000-0000-0000-000000000001', '11111111-0000-0000-0000-000000000001', '44444444-0000-0000-0000-000000000001',
   '22222222-0000-0000-0000-000000000001', 'synthetic.pdf', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'application/pdf', 10);
SQL

run_backup_tool() {
    # Runs one of the shipped scripts inside the shipped backup image, on the private network.
    local script="$1"; shift
    docker run --rm --network "$network" --entrypoint "/opt/myvita/${script}" \
        -e DB_HOST="${DB_HOST_OVERRIDE:-$source_db}" -e DB_PORT=5432 -e DB_NAME="${DB_NAME_OVERRIDE:-myvita}" \
        -e DB_USER=myvita -e PGPASSWORD="${PGPASSWORD_OVERRIDE:-$password}" \
        -v "${work_dir}/backups:/backups" "$backup_image" "$@"
}

step "Real backup with backup_db.sh"
mkdir -p "${work_dir}/backups"
run_backup_tool backup_db.sh /backups >"${work_dir}/backup.log" 2>&1 || { cat "${work_dir}/backup.log" >&2; exit 1; }
grep -q 'Backup completed successfully' "${work_dir}/backup.log"
grep -q "$password" "${work_dir}/backup.log" && { echo "FAIL: password appeared in backup log" >&2; exit 1; }
dump="$(find "${work_dir}/backups" -maxdepth 1 -name 'myvita_*.dump' -type f | head -n1)"
[ -s "$dump" ] && [ -s "${dump}.sha256" ]
[[ "$(basename "$dump")" =~ ^myvita_[0-9]{8}T[0-9]{6}Z\.dump$ ]]
echo "ok: $(basename "$dump") created with checksum"

step "Real connection failures must fail the backup without producing a dump"
before="$(count_dumps)"
expect_failure "backup with wrong password" in_env PGPASSWORD_OVERRIDE=wrong-password run_backup_tool backup_db.sh /backups
grep -q 'password authentication failed' "${work_dir}/last.log"
expect_failure "backup with PostgreSQL unavailable" in_env DB_HOST_OVERRIDE=no-such-db-host run_backup_tool backup_db.sh /backups
grep -q 'pg_dump failed' "${work_dir}/last.log"
expect_failure "backup of a non-existent database" in_env DB_NAME_OVERRIDE=does_not_exist run_backup_tool backup_db.sh /backups
grep -q 'does not exist' "${work_dir}/last.log"
[ "$(count_dumps)" = "$before" ] || { echo "FAIL: a failed backup left a dump behind" >&2; exit 1; }

step "Restore verification into an isolated PostgreSQL (with alembic upgrade/check)"
EXPECTED_ALEMBIC_REVISION="$head_revision" "${repo_root}/scripts/verify_restore.sh" "$dump" \
    --alembic-image "$backend_image" | tee "${work_dir}/verify.log"
grep -q 'RESTORE_VERIFY result=SUCCESS' "${work_dir}/verify.log"
for expected_count in clinics=1 users=2 patients=1 staff=1 appointments=1 conversations=1 messages=1 notifications=1 documents=1; do
    grep -q " ${expected_count}\b" "${work_dir}/verify.log" || { echo "FAIL: restored data missing ${expected_count}" >&2; exit 1; }
done
[ -z "$(docker ps -aq --filter label=myvita.restore-verify=true)" ] || { echo "FAIL: verification left containers behind" >&2; exit 1; }

step "Invalid backups must be rejected"
cp "$dump" "${work_dir}/truncated.dump"
truncate -s 200 "${work_dir}/truncated.dump" 2>/dev/null || head -c 200 "$dump" > "${work_dir}/truncated.dump"
expect_failure "verify a truncated dump" "${repo_root}/scripts/verify_restore.sh" "${work_dir}/truncated.dump"
printf 'not a postgres archive\n' > "${work_dir}/garbage.dump"
expect_failure "verify a non-archive file" "${repo_root}/scripts/verify_restore.sh" "${work_dir}/garbage.dump"
cp "$dump" "${work_dir}/tampered.dump"
sed "s/$(basename "$dump")/tampered.dump/" "${dump}.sha256" > "${work_dir}/tampered.dump.sha256"
printf 'x' >> "${work_dir}/tampered.dump"
expect_failure "verify a dump whose checksum does not match" "${repo_root}/scripts/verify_restore.sh" "${work_dir}/tampered.dump"
expect_failure "verify a missing file" "${repo_root}/scripts/verify_restore.sh" "${work_dir}/missing.dump"
EXPECTED_ALEMBIC_REVISION=not-the-head expect_failure "verify with wrong expected revision" \
    "${repo_root}/scripts/verify_restore.sh" "$dump"
grep -q '!= expected not-the-head' "${work_dir}/last.log"

step "restore_db.sh safety guards (real PostgreSQL)"
src_sql -c 'create database restore_target'
DB_NAME_OVERRIDE=restore_target run_backup_tool restore_db.sh "/backups/$(basename "$dump")" --yes >"${work_dir}/restore.log" 2>&1 \
    || { cat "${work_dir}/restore.log" >&2; exit 1; }
grep -q "Restore target: database='restore_target'" "${work_dir}/restore.log"
[ "$(docker exec "$source_db" psql -U myvita -d restore_target -Atc 'select count(*) from messages')" = "1" ]
echo "ok: restore into an empty database"
expect_failure "restore --yes over a populated database without --replace-existing" \
    in_env DB_NAME_OVERRIDE=restore_target run_backup_tool restore_db.sh "/backups/$(basename "$dump")" --yes
grep -q 'Refusing to overwrite' "${work_dir}/last.log"
DB_NAME_OVERRIDE=restore_target run_backup_tool restore_db.sh "/backups/$(basename "$dump")" --yes --replace-existing >"${work_dir}/replace.log" 2>&1 || { cat "${work_dir}/replace.log" >&2; exit 1; }
echo "ok: explicit --replace-existing restore"
expect_failure "restore into an unreachable target" \
    in_env DB_HOST_OVERRIDE=no-such-db-host run_backup_tool restore_db.sh "/backups/$(basename "$dump")" --yes
grep -q 'cannot connect to the restore target' "${work_dir}/last.log"
[ "$(src_sql -c 'select count(*) from messages')" = "1" ] || { echo "FAIL: source database changed" >&2; exit 1; }

step "Retention against real backups"
old="${work_dir}/backups/myvita_20000101T000000Z.dump"
cp "$dump" "$old"; cp "${dump}.sha256" "${old}.sha256"
touch -t 200001010000 "$old" "${old}.sha256"
printf 'unrelated\n' > "${work_dir}/backups/not-a-backup.dump"
touch -t 200001010000 "${work_dir}/backups/not-a-backup.dump"
docker run --rm --entrypoint /opt/myvita/prune_backups.sh -e BACKUP_RETENTION_DAYS=7 \
    -v "${work_dir}/backups:/backups" "$backup_image" /backups | tee "${work_dir}/prune.log"
grep -q 'removed=1' "${work_dir}/prune.log"
[ ! -e "$old" ] && [ ! -e "${old}.sha256" ] && [ -e "$dump" ] && [ -e "${work_dir}/backups/not-a-backup.dump" ]
echo "ok: only the expired myvita backup was removed"

echo "Restore verification integration tests passed."
