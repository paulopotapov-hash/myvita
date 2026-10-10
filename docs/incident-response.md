# Incident response and recovery runbook

Practical procedures for the technical incidents myVita can have. Use them together with:

- `privacy/INCIDENT_RESPONSE_PRIVACY.md`: personal-data breach assessment, severity and notification;
- `pilot-incident-response.md`: account and invitation cases;
- `operations.md`: alert handling, backups and disaster recovery.

**Not supplied yet.** Nothing in this runbook names people, contact addresses, legal responsibilities or response times. The organisation must fill the table below and keep it current. Until then, there is no staffed incident process.

## Roles and contacts (to be supplied by the organisation)

| Role | Responsibility | Name / backup | Contact (out-of-band, not the affected system) |
|---|---|---|---|
| Incident lead | Owns the incident, decisions and timeline | *to be supplied* | *to be supplied* |
| Infrastructure owner | Host, network, Docker, backups, TLS | *to be supplied* | *to be supplied* |
| Application owner | Code, releases, rollback | *to be supplied* | *to be supplied* |
| Privacy contact / DPO | Breach assessment, CNPD notification decision | *to be supplied* | *to be supplied* |
| Clinic contact (per clinic) | Clinical impact, patient communication | *to be supplied* | *to be supplied* |
| Hosting, object storage, e-mail and DNS providers | Provider-side incidents | *per contract* | *provider support channels* |
| Legal counsel | Regulatory and contractual obligations | *to be supplied* | *to be supplied* |

The regulatory notification deadlines (for example GDPR Art. 33's 72 hours) are assessed by the privacy contact. This runbook does not decide them.

## Common steps

1. **Declare.** Name the incident lead and open a timeline. Use UTC, and record who did what and when.
2. **Preserve evidence.** Keep proxy, backend and audit logs (the audit log is append-only), backups and container state. Do not run `docker compose down -v`, delete volumes or prune backups. Never copy clinical content, tokens or passwords into tickets or chat; reference request IDs and resource IDs instead.
3. **Contain** with the least destructive action that stops harm.
4. **Recover** from known-good code, configuration and backups. Verify before reopening traffic.
5. **Communicate** through the agreed channels. The privacy contact decides on notifications.
6. **Review** within the agreed time: timeline, impact, root cause, what worked, follow-ups with owners. Update this runbook.

## Scenarios

### Suspected credential compromise (user account)

- Deactivate the account (clinic admin; operator procedure for a clinic admin, `security/account-lifecycle.md`). Deactivation bumps `token_epoch` and revokes every session.
- Reset MFA if the second factor may be exposed. Issue a new reset link through a verified channel only.
- Review the audit trail for that actor: logins, views of patients, exports, denials. Determine which patients' data was viewed.
- If patient data was accessed without authorisation, treat it as a personal-data breach (next scenario).

### Suspected credential compromise (infrastructure or secrets)

Rotate the exposed secret at once (`p7-secret-management.md`), in this order of urgency:

| Secret | Effect of rotating it |
|---|---|
| `JWT_SECRET_KEY` | Logs everyone out (sessions revoked). |
| DB owner and runtime passwords | Run `migrate` to re-provision the runtime role. |
| `METRICS_TOKEN` | — |
| S3 keys | Revoke at the provider. Check bucket versioning and object lock; look for deleted or overwritten objects. |
| SMTP relay password | — |
| Alert secrets | — |
| TLS key | Revoke and reissue, `tls-certificates.md`. |
| `MFA_ENCRYPTION_KEY` | **Forces every staff member to re-enrol MFA.** Rotate only if the key itself was exposed. |
| age off-site backup key | Generate a new key pair. Re-encrypting old backups is a separate decision. |

Then check the logs for use of the old secret and rebuild from known-good images if the host itself is suspect.

### Unauthorised access or suspected data exposure

- Contain: deactivate the accounts involved; if the scope is unclear, put the application behind maintenance (stop the proxy) rather than leave it exposed.
- Scope with the audit trail (resource IDs, actors, times, `permission_denied` patterns) and proxy logs. Identify affected clinics and patients without copying their data.
- Hand the facts to the privacy contact for breach assessment and notification decisions (`privacy/INCIDENT_RESPONSE_PRIVACY.md`). Inform the affected clinic.
- Fix the root cause with a regression test before reopening.

### Application or database outage

- **Backend down or not ready.** Check `/health` and `/ready`, the logs by request ID and the last deployment. Roll back to the previous image digest if the release is the cause. Check database connectivity and pool exhaustion.
- **Database down.** Stop traffic; check the disk and PostgreSQL logs; never delete the data volume. If the data is damaged, recover into an **isolated** database first (`operations.md`, Restore drill). Switch only with the incident lead's approval and after verification.
- **Disk full.** Remove traffic before PostgreSQL is harmed. Free non-data space (old images, rotated logs). Never free space by deleting backups or the database volume.

### Backup failure

Alerts: `MyVitaBackupLastRunFailed`, `...MissingOrStale`, `MyVitaOffsiteBackupFailed`, `MyVitaDocumentsBackup...`.

- Do **not** prune or overwrite the last good copies.
- Read the backup container logs: authentication, network, bucket policy, disk, `pg_dump` errors.
- Fix the cause, run `run_scheduled_backup.sh` manually, and confirm `check_backup.sh` and the metrics.
- If off-site copies were missing for more than the RPO, record the exposure window and inform the incident lead.

### Failed restoration

- Never restore into production as a test. Never report a restore as successful because a file exists: `verify_restore.sh` must report `POSTGRES_RESTORE=OK DOCUMENTS_RESTORE=OK REFERENTIAL_INTEGRITY=OK`.
- Try the next older verified backup pair (database dump and documents archive), recording each attempt.
- If documents are missing for restored rows (`missing_files>0`), do not delete the rows; record them and look for a newer documents archive.
- Escalate to the infrastructure owner. Keep the failed artefacts for analysis.

### Document storage failure

- Alert: `MyVitaDocumentStorageUnavailable`. Uploads fail with 503 and existing downloads may fail.
- Check that the `myvita_documents` volume is mounted, writable by the backend user (`docker run --rm --entrypoint id <backend image> myvita`), and has free space.
- Run `verify_documents_storage.sh` to compare rows and files. Restore missing files from the documents archive (`restore_documents.sh`); never edit document rows by hand.

### Notification or e-mail delivery failure

- **In-app notifications** are written in the same transaction as the event. If they are missing, the event itself failed. Investigate the operation, not the notification.
- **E-mail** (`MyVitaEmailDeliveryFailing`, audit `delivery=failed`): check relay credentials, TLS, provider status and sender-domain reputation. Meanwhile admins hand links over manually; the UI says so. Re-issuing a link revokes the previous one.
- **Alert delivery** (`MyVitaAlertDeliveryFailing`, or the heartbeat service paging because pings stopped): treat as high priority, because you are partly blind. Check Alertmanager logs, the `alert-egress` network and the receiver secrets. Watch the dashboard manually until fixed.

### TLS or certificate failure

`MyVitaPublicHTTPSDown` or the expiry alerts: run `scripts/renew_tls_certificate.sh` and read its output. Check DNS, port 80 reachability for ACME, the CA's status and the proxy logs. Never disable HTTPS or HSTS to restore service.

## Closure checklist

- [ ] Service verified (health, readiness, smoke test, alerts resolved).
- [ ] Evidence preserved; secrets rotated where needed.
- [ ] Privacy assessment completed and recorded, notification decision documented.
- [ ] Timeline, root cause and follow-ups recorded, each with an owner.
- [ ] Runbook, alert rules or tests updated.
