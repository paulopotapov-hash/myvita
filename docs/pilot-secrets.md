# Pilot secrets inventory

Never commit credentials, invitation tokens, passwords, private keys or production environment files.

## Development

A gitignored `.env` may contain local-only values. It must use a development database and disposable credentials, never production values or real patient data.

## Test and dry-run

Generate unique temporary values for `JWT_SECRET_KEY`, database credentials, metrics token and dashboard password. Use an isolated database/Compose project and delete its data and environment file after the run.

## Real pilot

| Secret/configuration | Purpose | Required owner/store |
|---|---|---|
| `JWT_SECRET_KEY` | signs sessions and CSRF binding | application/security owner; approved secret store |
| PostgreSQL user/password/database | database access | infrastructure/database owner |
| host/disk encryption keys | data at rest | infrastructure/security owner |
| `METRICS_TOKEN` | internal metrics collector | monitoring owner |
| Grafana admin password | dashboard administration | monitoring owner |
| S3 access key/secret/session token | off-site backup | backup owner; prefix-limited identity |
| backup encryption/provider controls | backup confidentiality/immutability | backup/security owner |
| TLS private key/certificate automation | HTTPS | infrastructure owner |
| SMTP/webhook/paging credentials | invitation delivery/alerts | operations owner |

`PUBLIC_DOMAIN`, `ALLOWED_HOSTS`, `CORS_ORIGINS`, retention settings and contact destinations are sensitive operational configuration even when not secrets. Use exact approved values.

**BLOCKED — EXTERNAL INFRASTRUCTURE:** no approved production secret manager, credentials, rotation schedule or key custodians are present in this repository. Before a real pilot, document issuance, least privilege, rotation, emergency revocation and access review. Passwords must never be sent by email; invitation links require an approved authenticated private channel.
