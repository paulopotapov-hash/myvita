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
  "${OFFSITE_S3_PREFIX}/myvita_YYYYMMDDTHHMMSSZ.dump" /backups/recovery
```

The download script uses temporary files, validates SHA-256 and `pg_restore --list`, then publishes the local recovery dump atomically.

### Restore drill / disaster recovery

Never restore into the production database as a drill.

1. Select the newest verified object and record its timestamp.
2. Download it with `download_offsite_backup.sh`.
3. Create an isolated PostgreSQL database/container with no production traffic.
4. Point `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `PGPASSWORD`/`PGPASSFILE` at that isolated target.
5. Run `scripts/restore_db.sh <downloaded.dump> --yes`.
6. Run `alembic current` and, only if the dump predates the current release, `alembic upgrade head`.
7. Verify the expected tables, migration revision, fixture row counts, foreign-key integrity, login with synthetic test data, and representative list/read queries. Never use real patient data for a drill.
8. Destroy the isolated drill database and record duration, selected object, checks performed, and result.

For total server loss: provision a clean host, restore deployment secrets, deploy the same application version, download the newest verified off-site dump, restore it before routing traffic, apply required migrations, check `/health` and `/ready`, and only then enable the proxy.

Initial objectives are **RPO 24 hours** (daily backup schedule) and **RTO 4 hours** (provision, download, restore, verify). These are engineering targets, not contractual guarantees; measure drills and revise them as database size and operational staffing change.

Without real object-storage credentials, upload and the off-site restore drill remain blocked. Mocked tests prove control flow only; they are not evidence that a provider, bucket policy, encryption, or network path works.

## Monitoring (P2.3)

Start the production stack with the monitoring overlay:

```bash
POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=... \
JWT_SECRET_KEY=... PUBLIC_DOMAIN=... METRICS_TOKEN=... \
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
