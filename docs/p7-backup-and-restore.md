# P7-A production backup and restore

Status: **BLOCKED — REAL OFF-SITE BACKUP STORAGE REQUIRED**.

The application produces timestamped PostgreSQL custom dumps, SHA-256 sidecars, validates archives with `pg_restore --list`, writes failure/freshness metrics and supports S3-compatible upload. Backup starts only after database health and successful migrations. P6 proved local backup and isolated restore, not provider recovery.

## Required production policy

- Default frequency: daily (`0 3 * * *`), proposed RPO 24h and RTO 4h; owners must approve and measure both.
- Local retention defaults to 14 days; off-site defaults to 30 days. Legal/privacy retention may change these values.
- Object name: `<prefix>/myvita_YYYYMMDDTHHMMSSZ.dump` plus `.sha256`.
- Private bucket/container, TLS transport, encryption at rest, versioning and object lock/WORM where supported.
- Backup identity restricted to one prefix and required object operations; no public access.
- Provider audit logs, lifecycle policy, capacity/cost alerts and independent failure notification.

## Restore drill

1. Select a checksum-bearing off-site object and record release/database revision.
2. Download through `download_offsite_backup.sh` into an isolated recovery location.
3. Verify checksum and archive list before connecting to PostgreSQL.
4. Restore only into a new isolated database; never drill against production.
5. Confirm `alembic_version`, row/table sanity, current migrations and `/ready` using a non-public recovery stack.
6. Record elapsed download/restore/validation time, actual RPO/RTO and destroy synthetic recovery resources under an approved cleanup procedure.

Go-live requires a successful upload and timed restore from the real provider, encryption/object-lock evidence and named backup/on-call owners. Mock tests and local storage do not close this blocker.
