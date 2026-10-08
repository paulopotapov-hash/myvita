# myVita reliability and operations

This runbook covers local/off-site backups, monitoring, alerting, disaster recovery, and basic incident response. It contains no production credentials.

## Off-site backups (P2.2)

The backup container can copy each validated local custom-format PostgreSQL dump and its SHA-256 file to any S3-compatible object store. Upload happens only after `pg_restore --list` and checksum validation. The remote object size and checksum object are then confirmed with `HeadObject`; local retention runs only after this flow succeeds.

Required deployment secrets/configuration:

```env
OFFSITE_BACKUP_ENABLED=true
OFFSITE_S3_BUCKET=my-private-backup-bucket
OFFSITE_S3_PREFIX=myvita
OFFSITE_S3_REGION=eu-west-1
OFFSITE_S3_ENDPOINT=
OFFSITE_S3_SSE=AES256
OFFSITE_RETENTION_DAYS=30
AWS_ACCESS_KEY_ID=from-secret-store
AWS_SECRET_ACCESS_KEY=from-secret-store
```

`OFFSITE_S3_ENDPOINT` is blank for AWS and can point to a private S3-compatible endpoint for B2/R2/another provider. `OFFSITE_S3_SSE=AES256` requests provider-managed server-side encryption; use the provider's supported value. The bucket must deny public access. Use a dedicated, rotatable identity limited to list/get/put/delete within the configured prefix.

Prefer bucket versioning plus Object Lock/immutability configured at the provider. A 30-day governance retention protects against compromised server credentials better than application-side deletion. If Object Lock is enabled, configure provider lifecycle retention and expect the local pruning script's delete request to be rejected until the lock expires. Never grant the upload identity permission to change bucket policy, disable versioning, or shorten Object Lock.

List and retrieve backups:

```bash
docker compose -f docker-compose.prod.yml exec -T backup \
  aws s3 ls "s3://${OFFSITE_S3_BUCKET}/${OFFSITE_S3_PREFIX}/"

docker compose -f docker-compose.prod.yml exec -T backup \
  /opt/myvita/download_offsite_backup.sh \
  "${OFFSITE_S3_PREFIX}/postgres/myvita_YYYYMMDDTHHMMSSZ.dump" /backups/recovery
# or the newest database dump + documents archive together:
docker compose -f docker-compose.prod.yml exec -T backup \
  /opt/myvita/download_offsite_backup.sh --latest /backups/recovery
```

Off-site objects live under `<prefix>/postgres/` and `<prefix>/documents/` (older flat `<prefix>/myvita_*.dump` keys remain readable). The download script uses temporary files, validates SHA-256 and the archive (`pg_restore --list` or gzip/tar), then publishes atomically. Since Phase 7.1 the scheduled job also archives the private documents volume; database and documents must be recovered together — see [`p7-backup-and-restore.md`](p7-backup-and-restore.md) for the consistency model, documents restore and orphan checks.

### Restore drill / disaster recovery

Never restore into the production database as a drill.

1. Select the newest verified object and record its timestamp.
2. Download it with `download_offsite_backup.sh`.
3. Create an isolated PostgreSQL database/container with no production traffic.
4. Point `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `PGPASSWORD`/`PGPASSFILE` at that isolated target.
5. Run `scripts/verify_restore.sh <downloaded.dump> --alembic-image <backend image> --documents <downloaded documents archive>` (restores both into throwaway infrastructure and reports `POSTGRES_RESTORE=OK DOCUMENTS_RESTORE=OK REFERENTIAL_INTEGRITY=OK`), or `scripts/restore_db.sh <downloaded.dump> --yes` into your own empty isolated database. `restore_db.sh` refuses a non-empty target unless `--replace-existing` is given.
6. Run `alembic current` and, only if the dump predates the current release, `alembic upgrade head`.
7. Verify the expected tables, migration revision, fixture row counts, foreign-key integrity, login with synthetic test data, and representative list/read queries. Never use real patient data for a drill.
8. Destroy the isolated drill database and record duration, selected object, checks performed, and result.

For total server loss: provision a clean host, restore deployment secrets, deploy the same application version, download the newest verified off-site **dump and documents archive** (`--latest`), restore the database (`restore_db.sh`) and the documents volume (`restore_documents.sh`) before routing traffic, apply required migrations, run `verify_documents_storage.sh`, check `/health` and `/ready`, and only then enable the proxy. The full sequence is rehearsed by `scripts/test_offsite_recovery.sh`.

Initial objectives are **RPO 24 hours** (daily backup schedule) and **RTO 4 hours** (provision, download, restore, verify). These are engineering targets, not contractual guarantees; measure drills and revise them as database size and operational staffing change.

Without real object-storage credentials, upload and the off-site restore drill remain blocked. The local S3-compatible recovery test (`test_offsite_recovery.sh`) proves the scripts against a real S3 API, and mocked tests prove control flow; they are not evidence that a provider, bucket policy, encryption, or network path works.

## Monitoring (P2.3)

Start the production stack with the monitoring overlay:

```bash
POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=... \
JWT_SECRET_KEY=... PUBLIC_DOMAIN=... ALLOWED_HOSTS='["<PUBLIC_DOMAIN>"]' METRICS_TOKEN=... \
GRAFANA_ADMIN_PASSWORD=... \
docker compose -f docker-compose.prod.yml -f docker-compose.monitoring.yml up -d --build
```

The stack contains Prometheus, Grafana, Alertmanager, node-exporter, cAdvisor, postgres-exporter, blackbox-exporter, and a small internal metrics proxy. Prometheus, Alertmanager, exporters, and the backend metrics endpoint have no host port. Grafana binds only to `127.0.0.1:3000`; use an SSH tunnel for remote administration rather than publishing it directly.

cAdvisor is the only privileged monitoring container because it needs Docker/host visibility for per-container resource and restart metrics. Its host mounts are read-only and it has no published port. Treat access to the Docker host as privileged operational access and remove cAdvisor if the deployment platform already provides equivalent container metrics.

The metrics proxy injects `METRICS_TOKEN` on the internal network. The public proxy does not route `/metrics`. Metrics use bounded operational labels only—never users, clinics, patients, request bodies, cookies, JWTs, or clinical content.

The provisioned **myVita Operations** dashboard covers:

- proxy/backend availability and readiness;
- request rate, status classes, average application latency, and probe latency;
- host CPU, memory, and disk;
- container resource usage/restart signals;
- PostgreSQL reachability and connections;
- local/off-site backup freshness and last-run result;
- active alerts.

`UP` means proxy, backend readiness, and database probes succeed. `DEGRADED` means liveness remains available but readiness, backups, error rate, or a resource threshold is unhealthy. `DOWN` means the public proxy or backend liveness probe fails.

Useful validation commands:

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.monitoring.yml exec -T prometheus \
  promtool check config /etc/prometheus/prometheus.yml
docker compose -f docker-compose.prod.yml -f docker-compose.monitoring.yml exec -T prometheus \
  promtool check rules /etc/prometheus/alerts.yml
```

## Alerting (P2.4)

Rules define `critical` and `warning` severities:

- critical: proxy/backend/database down, backend not ready, local/off-site backup missing, stale, or failed, disk above 95%;
- warning: 5xx ratio above 5% for 10 minutes with meaningful traffic, disk above 85%, memory above 90%, CPU above 85%, PostgreSQL connections above 80%, repeated container restarts.

Durations in `monitoring/alerts.yml` deliberately avoid alerting on short restarts. Tune them only from observed load and incident history.

Alertmanager is intentionally provisioned with a receiver that has no external destination. Configure email, PagerDuty, Slack, Teams, or another approved human channel using deployment secrets before declaring P2.4 complete. Do not commit webhook URLs or SMTP passwords. After configuration, fire a controlled alert, confirm human delivery, recover the service, and confirm a resolved notification.

Controlled detection test:

1. Stop only the backend container; never stop or delete PostgreSQL data.
2. Confirm `probe_success` becomes `0`, then `MyVitaBackendDown`/`MyVitaBackendNotReady` becomes pending/firing after its configured duration.
3. Start the backend again and confirm the probes return to `1` and alerts resolve.
4. For backup alert testing, point `BACKUP_METRICS_DIR` at a temporary directory and use `write_backup_metrics.sh local-failure`; do not corrupt a real backup.

## Incident response

1. **Detect:** acknowledge the alert and identify severity, affected component, start time, and current user impact.
2. **Confirm:** check independent health probes, recent deployment changes, logs by request ID, host resources, database health, and backup freshness. Do not copy sensitive payloads into tickets/chat.
3. **Contain:** stop harmful automation or remove traffic from an unhealthy instance. Preserve logs and valid backups; do not delete evidence or run destructive database commands casually.
4. **Recover:** rollback the last known risky change or restore the affected component. For data loss, follow the isolated verification and disaster-recovery procedure above.
5. **Verify:** confirm health/readiness, representative synthetic workflows, database integrity, metrics, alerts, and backup operation. Watch for recurrence.
6. **Document:** record timeline, impact, root cause, actions, recovery evidence, and concrete follow-ups. Rotate any credential suspected of exposure.

Scenario guidance:

- **Backend down:** remove traffic, inspect proxy/backend health and logs by request ID, check the last migration/deploy, rollback the application image if appropriate, then verify synthetic login and readiness.
- **Database down:** stop writes/traffic, check storage and PostgreSQL health without deleting volumes, recover the service or provision an isolated replacement, and use only a checksum-verified backup through the restore procedure.
- **Disk full:** remove traffic before PostgreSQL is harmed, identify the consuming filesystem, preserve database and backup evidence, expand or safely reclaim non-data space, then verify database integrity and run a backup.
- **Backup failure:** do not prune the last known-good copy; inspect the backup result metric and storage/network/authentication error, repair it, run a new backup, validate checksum/archive, and schedule an isolated restore drill.
- **Authentication issue:** determine whether it is configuration, rate limiting, session invalidation, or suspected compromise. Never bypass password checks. Restore service safely; for compromise, invalidate sessions and rotate affected credentials.
- **Security incident:** restrict access, preserve immutable logs/backups, record scope and timeline, rotate exposed credentials, assess data exposure with the approved privacy process, recover from a known-good release, and notify the designated incident/privacy roles once those roles exist.

## Phase 4 drill evidence (local rehearsal, synthetic data)

Run on 2026-10-05 against the production topology (`docker-compose.prod.yml` + `prod-http` + `monitoring` overlays) on a developer machine, **not** on real staging (none exists yet). Alerts were routed to a throwaway local webhook; the off-site target was a local S3-compatible server (moto), so it proves the code path, not a separate failure domain.

| Check | Result |
|---|---|
| Prometheus targets (backend, postgres, host, containers, blackbox, alertmanager) | all up; public `/metrics` returns 404 |
| `promtool check rules` / `test rules` | 17 rules valid; unit tests pass |
| Local backup (`pg_dump -Fc`, checksum, `pg_restore --list`) | success, metrics `last_run_success=1` |
| Off-site upload, size check, retention | success; a prior unreachable-endpoint run correctly reported `offsite_last_run_success=0` |
| Download from off-site, checksum verified, restore into isolated PostgreSQL | restore 0.37 s for a 48 KB dump |
| Restored data vs source | all 12 tables identical (row counts and content md5); Alembic `f6a7b8c9d0e1`; a backend booted on the restored DB accepted a synthetic doctor login |
| Drill: PostgreSQL stopped | `/ready` 503 immediately, `/health` stayed 200; `PostgreSQLDown` delivered to the receiver at +132 s; `MyVitaBackendNotReady` at +157 s |
| Recovery: PostgreSQL started | `/ready` 200 after 3 s; login worked; alerts resolved within about 50 s; row counts unchanged |

Supported by this evidence: RPO 24 h (daily schedule, off-site copy after each run) and an RTO well inside 4 h for a database of this size. The restore time is **not** representative of a clinic database; repeat the timed restore on real staging and again as data grows.

Defects found and fixed during the drill: the disk alerts and dashboard counted read-only `erofs`/`squashfs`/`iso9660` mounts (always 100% used) and fired a false `HostDiskUsageCritical`; containers had no log rotation, so Docker logs could grow without bound (now `json-file`, 10 MB x 5 per service).

Known limits (not closed by this phase):

- Alertmanager has no real receiver (`pending-human-destination`); a staffed email/webhook receiver is required before a pilot.
- Backups and the database share one host and the backup container holds both database and off-site credentials; a real off-site bucket with prefix-scoped, write-only credentials, encryption and retention policy is still to be provisioned and tested.
- Logs live only in rotated container logs; central aggregation and a retention period are undecided. Metrics have request counts and duration sum/count, but no latency histogram, so there is no p95 alert.
- TLS, Secure cookies, JSON production logs and a real staging deployment are unverified (Phase 3 is blocked on infrastructure).
