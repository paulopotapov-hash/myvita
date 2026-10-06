# P7-A secret management

Status: **BLOCKED — APPROVED SECRET MANAGER, VALUES AND CUSTODIANS REQUIRED**.

The repository is provider-neutral. AWS Secrets Manager, GCP Secret Manager, Azure Key Vault or Vault are architectural options only; selection depends on the actual host and organization. Secrets must be injected at runtime, never baked into images, frontend bundles, Compose files, logs or Git.

| Secret | Requirement | Scope | Rotation |
|---|---|---|---|
| PostgreSQL owner user/password (`POSTGRES_USER`/`POSTGRES_PASSWORD`) | mandatory | db/migrate/backup/exporter — **never the backend** | scheduled, incident, staff change |
| Runtime database role (`APP_DB_ROLE`/`APP_DB_PASSWORD`, ≥16 chars, role ≠ owner) | mandatory | backend (connects as it), migrate (provisions it) | scheduled/incident; re-run migrate to apply |
| MFA encryption key (`MFA_ENCRYPTION_KEY`, urlsafe base64 of 32 bytes) | mandatory | backend/migrate | **do not rotate casually**: changing it invalidates every MFA enrolment (mass re-enrolment). Back it up in the secret manager |
| Privacy fingerprint key (`PRIVACY_FINGERPRINT_KEY`, ≥32 chars) | mandatory | backend/migrate | scheduled/incident; only breaks correlation of older log fingerprints |
| JWT signing material | mandatory | backend/migrate | scheduled/incident; revokes sessions |
| Metrics token | mandatory with monitoring | backend/metrics proxy | scheduled/incident |
| Grafana bootstrap password | mandatory | Grafana only | immediately after bootstrap/incident |
| Registry pull credential | mandatory for private images | Docker host only | short-lived/incident |
| S3 access/session credentials | mandatory for off-site backup | backup only, prefix-limited | prefer short-lived; incident |
| Backup/provider encryption key | mandatory when provider-managed encryption is insufficient | backup/provider | provider policy |
| TLS private key | mandatory | TLS terminator only | renewal/compromise |
| SMTP/email credential | required for recovery/invitations if selected | delivery service only | provider/incident |
| Alert webhook/pager credential | required for human alerts | Alertmanager only | provider/incident |

Provision separate runtime identities, deny secret enumeration where possible, audit reads, document break-glass access and test rotation. Render secrets into a root-owned `0600` runtime file or native secret mount outside the repository; avoid process arguments. `.env.production.example` is a schema of placeholders, not a production secret store.

Before deployment, run the preflight, secret scan, access review and a rotation rehearsal. Record owner, backup owner, source path/version, consumers, creation/expiry and last rotation without recording the secret value.
