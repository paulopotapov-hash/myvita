# P7-A secret management

Status: **BLOCKED — APPROVED SECRET MANAGER, VALUES AND CUSTODIANS REQUIRED**.

The repository is provider-neutral. AWS Secrets Manager, GCP Secret Manager, Azure Key Vault or Vault are architectural options only; selection depends on the actual host and organization. Secrets must be injected at runtime, never baked into images, frontend bundles, Compose files, logs or Git.

| Secret | Requirement | Scope | Rotation |
|---|---|---|---|
| PostgreSQL user/password | mandatory | db/backend/migrate/backup/exporter | scheduled, incident, staff change |
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
