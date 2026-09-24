#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf "$test_root"' EXIT
fake_bin="${test_root}/bin"
backup_dir="${test_root}/backups"
mkdir -p "$fake_bin" "$backup_dir"

cat > "${fake_bin}/pg_dump" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
output=""
while [ "$#" -gt 0 ]; do
    if [ "$1" = "-f" ]; then output="$2"; shift 2; else shift; fi
done
[ "${FAKE_DUMP_MODE:-ok}" != "fail" ] || exit 42
printf 'valid custom archive fixture\n' > "$output"
EOF

cat > "${fake_bin}/pg_restore" <<'EOF'
#!/usr/bin/env bash
[ "${FAKE_RESTORE_MODE:-ok}" != "fail" ] || exit 43
exit 0
EOF
chmod 0555 "${fake_bin}/pg_dump" "${fake_bin}/pg_restore"

export PATH="${fake_bin}:$PATH"
export DB_HOST=db DB_PORT=5432 DB_NAME=myvita DB_USER=myvita PGPASSWORD=test-only

"${repo_root}/scripts/backup_db.sh" "$backup_dir" >/dev/null
dump="$(find "$backup_dir" -maxdepth 1 -name 'myvita_*.dump' -type f | head -n1)"
[ -n "$dump" ] && [ -s "$dump" ]
[ -s "${dump}.sha256" ]
[ -z "$(find "$backup_dir" -maxdepth 1 -name '*.tmp*' -print -quit)" ]
(cd "$backup_dir" && sha256sum -c "$(basename "${dump}.sha256")" >/dev/null)
BACKUP_MAX_AGE_HOURS=36 "${repo_root}/scripts/check_backup.sh" "$backup_dir" >/dev/null

before_count="$(find "$backup_dir" -name 'myvita_*.dump' | wc -l | tr -d ' ')"
if FAKE_DUMP_MODE=fail "${repo_root}/scripts/backup_db.sh" "$backup_dir" >/dev/null 2>&1; then
    echo "ERROR: a failed pg_dump was reported as success" >&2; exit 1
fi
after_count="$(find "$backup_dir" -name 'myvita_*.dump' | wc -l | tr -d ' ')"
[ "$before_count" = "$after_count" ]
[ -z "$(find "$backup_dir" -maxdepth 1 -name '*.tmp*' -print -quit)" ]

# A filesystem/path error must fail without affecting the existing backup.
blocked_output="${test_root}/not-a-directory"
printf blocked > "$blocked_output"
if "${repo_root}/scripts/backup_db.sh" "${blocked_output}/backups" >/dev/null 2>&1; then
    echo "ERROR: an unwritable output path was reported as success" >&2; exit 1
fi
[ "$before_count" = "$(find "$backup_dir" -name 'myvita_*.dump' | wc -l | tr -d ' ')" ]

sleep 1
if FAKE_RESTORE_MODE=fail "${repo_root}/scripts/backup_db.sh" "$backup_dir" >/dev/null 2>&1; then
    echo "ERROR: a failed validation was reported as success" >&2; exit 1
fi
[ "$before_count" = "$(find "$backup_dir" -name 'myvita_*.dump' | wc -l | tr -d ' ')" ]

old_dump="${backup_dir}/myvita_20000101T000000Z.dump"
printf old > "$old_dump"
sha256sum "$old_dump" > "${old_dump}.sha256"
touch -t 200001010000 "$old_dump" "${old_dump}.sha256"
printf incomplete > "${backup_dir}/.myvita_20000101T000000Z.dump.tmp.fixture"
BACKUP_RETENTION_DAYS=14 "${repo_root}/scripts/prune_backups.sh" "$backup_dir" >/dev/null
[ ! -e "$old_dump" ] && [ ! -e "${old_dump}.sha256" ]
[ -e "$dump" ] && [ -e "${dump}.sha256" ]
[ -e "${backup_dir}/.myvita_20000101T000000Z.dump.tmp.fixture" ]

printf corrupted >> "$dump"
if BACKUP_MAX_AGE_HOURS=36 "${repo_root}/scripts/check_backup.sh" "$backup_dir" >/dev/null 2>&1; then
    echo "ERROR: a corrupt checksum was reported as valid" >&2; exit 1
fi

echo "Backup script tests passed."
