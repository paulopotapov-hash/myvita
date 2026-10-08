# P7 backup, restore and disaster recovery (PostgreSQL + documents)

Status: **BLOCKED — REAL OFF-SITE BACKUP STORAGE REQUIRED** for go-live (see [Go-live gate](#go-live-gate)). Local backup, document storage backup, off-site upload/download and full recovery are implemented and tested end to end against throwaway PostgreSQL and a local S3-compatible store. No real provider has been exercised.

## Architecture

```text
db (postgres:16, myvita_pg_data)        backend ──writes──► myvita_documents (DOCUMENT_STORAGE_DIR)
        │ pg_dump -Fc                                              │ read-only mount (/documents)
        ▼                                                          ▼
                     backup service (backup/Dockerfile, cron)
                     1. myvita_<UTC>.dump            + .sha256
                     2. myvita_documents_<UTC>.tar.gz + .sha256
                                   │  volume myvita_backups (/backups, 0700)
                                   ▼  optional, OFFSITE_BACKUP_ENABLED=true
              s3://$OFFSITE_S3_BUCKET/$OFFSITE_S3_PREFIX/postgres/…
              s3://$OFFSITE_S3_BUCKET/$OFFSITE_S3_PREFIX/documents/…
```

- The backup service is a separate container that nothing depends on. A backup failure never stops or delays the API; FastAPI does no scheduling or backup work. A failed run on start is logged and the scheduler still starts.
- The cron job runs as root inside the backup container only to read the backend-owned documents volume, which is mounted **read-only**. Database steps drop to the unprivileged `postgres` user.
- `myvita_backups` is separate from both data volumes, but **a backup on the same physical disk/host as the data is NOT disaster recovery**. Only the off-site copy survives loss of the host.

## Consistency model (database vs documents)

The two backups are independent; they are **not** one atomic snapshot. Each run takes them in a fixed order:

1. `pg_dump` (a consistent snapshot of the database at time *T_db*);
2. then the documents archive (files present at time *T_docs* ≥ *T_db*, seconds to minutes later).

Both timestamps appear in the file names and in the log. The backend writes a document's file **before** committing its row and never modifies a stored file. So every document row in the dump already had its complete file when the archive started. The only gaps come from activity between *T_db* and *T_docs*:

| During the window | After restore | Reported by the check as | Action |
|---|---|---|---|
| A new upload | The file is restored, but its row is not | `orphan_file` | Harmless; review, then keep or remove manually |
| A deletion | The row is restored, but its file is not | `missing_file` | The document was deleted on purpose; review and remove the row manually if needed |
| An upload still being written | Not affected: each file is copied to private staging and hashed there | — | — |

Interrupted deletes (`.pending-*`) are never archived. Nothing is ever deleted automatically. A run during low traffic (default 03:00 UTC) makes these cases rare.

## Local backups

| Setting | Default | Notes |
|---|---|---|
| `BACKUP_SCHEDULE` | `0 3 * * *` | Five-field cron, in `BACKUP_TIMEZONE` (default UTC) |
| `BACKUP_RETENTION_DAYS` | `14` | Local dumps **and** documents archives older than N days are deleted |
| `DOCUMENTS_BACKUP_ENABLED` | `true` (prod compose) | Archives `/documents` (read-only `myvita_documents` mount) |
| `BACKUP_RUN_ON_START` | `true` | One run when the service starts |

Database credentials reuse `POSTGRES_*` through a `0600` PGPASSFILE; passwords never appear in argv, file names or logs.

- **PostgreSQL** (`backup_db.sh`): `pg_dump -Fc` to a temp file, then `pg_restore --list`, then a SHA-256 sidecar, then an atomic rename.
- **Documents** (`backup_documents.sh`):
  1. Copies every storage object (32-hex key) into private staging.
  2. Writes `MANIFEST.sha256` (one digest per file) and `BACKUP_INFO` (`created_at`, `file_count`, `total_bytes`).
  3. Builds a `tar.gz`.
  4. Checks the gzip and tar listing and the expected file count, extracts it to a scratch area and verifies the manifest.
  5. Writes the sidecar and renames atomically.

  A partial archive is never visible under a final name. Files are 0600 in a 0700 directory, and no document content or original file name is logged.
- **Retention** (`prune_backups.sh`) only matches `myvita_<ts>.dump` and `myvita_documents_<ts>.tar.gz` plus their sidecars, and never today's files. It logs `removed=<n>`.

```bash
# Manual run of the full job (database, documents, off-site upload if enabled, retention)
docker compose -f docker-compose.prod.yml exec -T backup /opt/myvita/run_scheduled_backup.sh
docker compose -f docker-compose.prod.yml exec backup ls -lh /backups
# Stale/invalid detection: exit 0 only if both newest backups are fresh (< BACKUP_MAX_AGE_HOURS, default 36), checksummed and readable
docker compose -f docker-compose.prod.yml exec -T backup /opt/myvita/check_backup.sh /backups
#   -> BACKUP_STATUS postgres=OK documents=OK
```

## Off-site storage (S3-compatible)

Any S3 API provider works through the bundled AWS CLI: AWS S3, Cloudflare R2, MinIO, Backblaze B2, SeaweedFS and others. Settings live in the deployment's secret environment (placeholders in `.env.production.example`); never commit them.

| Variable | Purpose |
|---|---|
| `OFFSITE_BACKUP_ENABLED` | `true` to upload after each run |
| `OFFSITE_S3_BUCKET`, `OFFSITE_S3_PREFIX` (default `myvita`) | Destination; the prefix must be a plain non-empty path |
| `OFFSITE_S3_ENDPOINT` | Required for non-AWS providers (`https://…`) |
| `OFFSITE_S3_REGION` | Region (`us-east-1` default) |
| `OFFSITE_S3_SSE` | `AES256` (default), `aws:kms`, or `none` for providers without SSE-S3 |
| `OFFSITE_RETENTION_DAYS` | Default 30 |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (`AWS_SESSION_TOKEN`) | A **backup-only** identity limited to the prefix; never the application's or an admin's credentials |

Object layout: `<prefix>/postgres/myvita_<ts>.dump(.sha256)` and `<prefix>/documents/myvita_documents_<ts>.tar.gz(.sha256)`. Older flat keys (`<prefix>/myvita_<ts>.dump`) are still downloadable and pruned.

- **Upload** (`upload_offsite_backup.sh <file>`):
  1. Verifies the local checksum and archive.
  2. Uploads the data, then its sidecar. A sidecar off-site therefore means the data upload completed.
  3. Checks both remote sizes and reports the object key.

  Local files are never deleted because an upload succeeded. To upload a backup set manually:

  ```bash
  docker compose -f docker-compose.prod.yml exec -T backup /opt/myvita/upload_offsite_backup.sh /backups/myvita_<ts>.dump
  docker compose -f docker-compose.prod.yml exec -T backup /opt/myvita/upload_offsite_backup.sh /backups/myvita_documents_<ts>.tar.gz
  ```

- **Download** (`download_offsite_backup.sh <key> [dir]`, or `--latest [dir]` for the newest dump and the newest documents archive): verifies the digest and archive before publishing anything. Existing files are never overwritten.
- **Retention** (`prune_offsite_backups.sh`) deletes only exact myVita backup names under `<prefix>/` whose embedded timestamp is older than `OFFSITE_RETENTION_DAYS`. It always keeps the newest dump and the newest documents archive, and never touches other prefixes or names.
- **Encryption and immutability** are provider settings. myVita requests SSE (unless `none`) but does not encrypt client-side and does not change bucket configuration. `check_offsite_bucket.sh` reports what the provider actually has: `OFFSITE_BUCKET … versioning=Enabled|Suspended|Disabled object_lock=Enabled|Disabled`. It exits non-zero unless versioning is enabled. Production should enable versioning and object lock/WORM with a retention at least as long as `OFFSITE_RETENTION_DAYS`, TLS-only access and provider audit logs. Do not describe backups as immutable unless that check shows object lock.

## Verification

`pg_dump` succeeding is not evidence of recoverability. On any host with Docker (operator workstation, CI, recovery host), and never against live data:

```bash
docker build -t myvita-backend:verify backend    # same release as production
scripts/verify_restore.sh myvita_<ts>.dump --alembic-image myvita-backend:verify --documents myvita_documents_<ts>.tar.gz
#   POSTGRES_RESTORE=OK DOCUMENTS_RESTORE=OK REFERENTIAL_INTEGRITY=OK
```

It restores into a throwaway PostgreSQL on an internal network (no ports, tmpfs) and a private temp directory, then checks:

- alembic upgrade/check and the revision;
- all tables, tenant constraints, indexes and validated foreign keys;
- row counts, representative reads and clinic-consistency invariants;
- that the documents manifest matches;
- that every `documents` row has its file (`missing_files=0`). Orphans fail unless `VERIFY_ALLOW_ORPHAN_FILES=true` (see the consistency model).

Everything it created is destroyed afterwards. With `BACKUP_METRICS_DIR` set, the result is recorded as `myvita_recovery_verification_*`. Run it at least weekly against the newest **off-site** set.

On a restored system, `verify_documents_storage.sh <storage_dir> [--allow-orphans]` (with `DB_*` set) compares the `documents` table with the files on disk, read-only:
`DOCUMENTS_CONSISTENCY records=… stored_files=… missing_files=0 orphan_files=0 pending_deletes=0 unexpected_entries=0`. It lists only storage keys, never deletes anything, and exits 1 on discrepancies.

## Recovery procedures

Common rules:
- Stop writers first: `docker compose -f docker-compose.prod.yml stop proxy backend frontend`.
- Verify the chosen set with `verify_restore.sh` before restoring.
- Restore into empty targets whenever possible. Both restore scripts refuse a populated target unless `--replace-existing` is given, and they verify checksums and archives first.
- Record which set was used, the timings and the actual data-loss window.

**Database lost or corrupted (documents intact):**
1. Pick the last dump before the incident.
2. Run `restore_db.sh <dump> --yes` into an empty database, or add `--replace-existing` to replace it in place.
3. Run `docker compose … run --rm migrate`.
4. Run `verify_documents_storage.sh /documents --allow-orphans` from the backup service. Uploads made after the dump appear as orphans; review them, don't delete them blindly.

**Documents volume lost (database intact):** restore the newest archive into the (new, empty) volume:

```bash
docker run --rm -v <project>_myvita_backups:/backups:ro -v <project>_myvita_documents:/restore \
  --entrypoint /opt/myvita/restore_documents.sh <backup image> /backups/myvita_documents_<ts>.tar.gz /restore --owner <uid:gid of myvita in the backend image>
```

`docker volume ls` shows the real volume names, and `docker run --rm --entrypoint id <backend image> myvita` shows the uid/gid. Then run `verify_documents_storage.sh`. Documents uploaded after that archive cannot be recovered and appear as `missing_file`.

**Complete host loss:**
1. Provision a host and deploy the same release and secrets (`docs/p7-deployment-runbook.md`).
2. Start only `db`.
3. Run `download_offsite_backup.sh --latest /backups/recovery` (from `docker compose run --rm --no-deps --entrypoint /opt/myvita/download_offsite_backup.sh backup …`).
4. Run `verify_restore.sh` on the set.
5. Restore the database with `--yes` into the empty database, then restore the documents into the empty volume as above.
6. Run `migrate`, `verify_documents_storage.sh` and `check_backup.sh`.
7. Start the stack. Check `/health`, `/ready`, a login and a document download with a synthetic account, and only then enable the proxy.

The whole flow is rehearsed by `scripts/test_offsite_recovery.sh`: it creates data through the API, runs the scheduled job with off-site upload, destroys everything, recovers from the object store only, and downloads every document byte-for-byte.

## Monitoring and alerting

`/metrics/myvita_backup.prom` (node-exporter textfile, volume `myvita_backup_metrics`) exposes:
- the last success timestamp and last-run status for PostgreSQL, documents and off-site;
- the last dump and archive sizes and the archived file count;
- `myvita_recovery_verification_*`.

`monitoring/alerts.yml` alerts on:
- failed or stale (> 36 h) database, documents and off-site backups;
- failed or stale (> 8 days) recovery verification, once that has reported at least once.

Routing those alerts to people (Alertmanager receivers, on-call) is still a deployment task. Without it, use `check_backup.sh` and `check_offsite_bucket.sh` exit codes and the container logs.

## Recovery objectives (initial operational targets, not SLAs)

- **RPO 24 h** with the daily schedule: up to a day of database changes and document uploads can be lost. More frequent schedules lower it (`0 */6 * * *` → about 6 h), at the cost of storage and run time. Sub-hour RPO needs WAL archiving/PITR and continuous file replication, which is not implemented.
- **RTO 4 h** = provision a host + download + verify + restore the database and documents + migrate + checks + DNS/proxy. Locally, the full recovery test (small data set) completes in about a minute. Measure real drills with production-sized data and the real provider, and revise.

## Security

- Backups contain all patient data and documents. `.gitignore` excludes `*.dump`, `*.tar.gz`, `*.sha256`, `backups/` and temp/staging names. Never use real patient data in drills or tests; the tests use synthetic data and test-only credentials.
- All backup files are 0600 in 0700 directories. Restored documents are 0600 in a 0700 directory, owned by the backend user. The documents volume is mounted read-only for backups and is never served over HTTP.
- No password, access key, URL with credentials or document content is logged (the tests assert this). Failed uploads publish no "success" metric, and an incomplete archive never gets a final name.
- At rest: encrypted disks/volumes on the host, and provider SSE plus versioning/object lock off-site. In transit: an HTTPS endpoint only.

## Limitations

- No PITR/WAL archiving; RPO is bounded by the schedule.
- Database and documents backups are sequential, not atomic (see the consistency model).
- True off-site recovery requires an external bucket. Tests use a local SeaweedFS S3 server, and no real provider has been exercised.
- Encryption at rest and immutability depend entirely on provider configuration.
- Alert delivery depends on the external monitoring/on-call setup.
- RPO/RTO are targets, not SLAs.

## Go-live gate

Go-live requires:
- a real bucket with a prefix-scoped backup identity, SSE, versioning and object lock (`check_offsite_bucket.sh` exit 0);
- a successful scheduled upload of both streams;
- a timed recovery from the real provider using `verify_restore.sh --documents` plus a staging restore;
- alert routing to named backup and on-call owners.

Local storage and CI drills do not close this blocker.
