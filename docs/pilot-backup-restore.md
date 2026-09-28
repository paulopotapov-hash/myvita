# Pilot backup and restore

## Objectives

- proposed RPO: 24 hours;
- proposed RTO: 4 hours;
- local backup: daily, custom-format PostgreSQL dump, checksum validation;
- local retention: 14 days;
- off-site retention: proposed 30 days with versioning/Object Lock or equivalent;
- encryption: encrypted host/volume plus provider-supported encryption; keys must be externally managed.

These are engineering targets pending owner approval and measured restore drills.

## Backup procedure

Use the production `backup` service or `scripts/backup_db.sh`. A run is successful only after `pg_restore --list` and SHA-256 verification. Do not prune the last known-good backup after a failed run. `scripts/check_backup.sh` validates freshness; off-site upload additionally verifies remote object metadata.

## Isolated restore procedure

1. Declare the restore purpose and select a checksum-verified dump.
2. Provision an isolated PostgreSQL target with no application traffic.
3. Download the off-site object if applicable and verify checksum/archive.
4. Run `scripts/restore_db.sh <dump> --yes` against the isolated target.
5. Check Alembic revision, expected tables, referential integrity and representative synthetic login/read flows.
6. Record start/end time, source timestamp, release, checks and outcome.
7. Destroy the isolated target and synthetic data after approval of the evidence.

Never test restore over the live database. A local or mocked backup test is not off-site disaster-recovery evidence.

## Gate

Local backup scripts and failure-mode tests are READY. A real encrypted/immutable off-site destination, provider credentials, successful upload, isolated restore drill and named backup owner are **BLOCKED — EXTERNAL INFRASTRUCTURE**.
