# myVita production deployment

This is the release runbook for a single-host Docker deployment. It intentionally does not contain a domain, certificate, production credential, or patient data.

## External prerequisites

Before go-live, the operator must provide a DNS name, TLS certificate/renewal mechanism, encrypted host storage, a secret manager, a private S3-compatible backup bucket, and a staffed alert destination. These are deployment inputs, not repository defaults.

Required application values are `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `JWT_SECRET_KEY` (at least 32 random bytes), `PUBLIC_DOMAIN`, and `ALLOWED_HOSTS` (JSON, for example `["<PUBLIC_DOMAIN>"]`). Optional overrides include `CORS_ORIGINS`, `INVITATION_EXPIRE_HOURS`, `BACKUP_*`, `OFFSITE_*`, `AWS_*`, `METRICS_TOKEN`, and `GRAFANA_ADMIN_PASSWORD`. Store secrets outside Git and pass them through the platform secret manager or a non-committed environment file.

Environment inventory:

- Application: `APP_NAME`, `ENVIRONMENT`, `DEBUG`, `DATABASE_URL`, `MAX_REQUEST_BODY_BYTES`.
- Session/security: `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `COOKIE_NAME`, `COOKIE_SECURE`, `COOKIE_SAMESITE`, `CSRF_COOKIE_NAME`, `CSRF_HEADER_NAME`.
- Network policy: `PUBLIC_DOMAIN`, `HTTP_PORT`, `CORS_ORIGINS`, `CORS_ALLOW_METHODS`, `CORS_ALLOW_HEADERS`, `ALLOWED_HOSTS`, `TRUSTED_PROXIES`; `LOCAL_ORIGIN` is only for the local HTTP overlay.
- Registration: `ALLOW_PUBLIC_CLINIC_ONBOARDING`, `ALLOW_PUBLIC_PATIENT_REGISTRATION`, `INVITATION_EXPIRE_HOURS`.
- Database container: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`.
- Local backup: `BACKUP_SCHEDULE`, `BACKUP_RETENTION_DAYS`, `BACKUP_RUN_ON_START`, `BACKUP_TIMEZONE`.
- Off-site backup: `OFFSITE_BACKUP_ENABLED`, `OFFSITE_S3_BUCKET`, `OFFSITE_S3_PREFIX`, `OFFSITE_S3_ENDPOINT`, `OFFSITE_S3_REGION`, `OFFSITE_S3_SSE`, `OFFSITE_RETENTION_DAYS`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optional temporary `AWS_SESSION_TOKEN`.
- Monitoring: `METRICS_TOKEN`, `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`, `GRAFANA_PORT`, `PROMETHEUS_RETENTION`.

Production Compose fixes `ENVIRONMENT=production`, `DEBUG=false`, `COOKIE_SECURE=true`, and the trusted proxy network address. Do not override these controls without a reviewed topology change. `backend/.env.example` documents application defaults; Compose files are the source of truth for container-only variables.

Do not enable `ALLOW_PUBLIC_CLINIC_ONBOARDING` or `ALLOW_PUBLIC_PATIENT_REGISTRATION` for normal operation. Controlled onboarding uses invitations as described in `clinic-onboarding.md`.

## Release sequence

1. Review the release commit and confirm CI is green.
2. Verify a recent off-site backup and its checksum. For schema-risking releases, perform an isolated restore drill first.
3. Build immutable images from the reviewed commit. Do not mount source directories.
4. Run `docker compose -f docker-compose.prod.yml config --quiet` with the deployment environment.
5. Start `db`; wait for its healthcheck. Run the one-shot `migrate` service. The backend is already gated on migration success.
6. Start the remaining services, then verify `/health`, `/ready`, the login page, a synthetic invitation flow, and monitoring targets. Never create synthetic clinical records in production.
7. Enable traffic only after TLS, backups, metrics, and human alert delivery are confirmed.

The compose stack exposes only the reverse proxy. PostgreSQL is restricted to the internal data network; frontend and backend have no host ports. Containers drop Linux capabilities where practical, use `no-new-privileges`, and have explicit graceful-stop windows. The backend filesystem is read-only with a small temporary filesystem.

## TLS and domains

Use `docker-compose.prod-tls.yml.example` and `proxy/nginx.tls.conf.template.example` only after real DNS and certificate paths exist. Keep private keys outside the repository. Terminate TLS at the proxy, redirect HTTP to HTTPS, keep secure cookies enabled, and set `PUBLIC_DOMAIN`, `ALLOWED_HOSTS`, and `CORS_ORIGINS` to the exact approved host/origin. Validate certificate renewal and an HTTPS request before routing users.

## Rollback and shutdown

Application rollback means deploying the previous reviewed image. Database rollback is not automatic: review the migration and recovery impact before any Alembic downgrade. Prefer a forward fix; restore only under the incident runbook with an explicitly verified target and backup.

For planned shutdown, remove traffic, run `docker compose -f docker-compose.prod.yml stop`, and allow the configured grace periods to elapse. Do not delete volumes. Confirm the final backup result before host maintenance.

## Go-live gates

- CI, migrations, image builds, and security scans pass.
- Real DNS and valid renewable TLS are verified.
- Secrets are injected from an approved store and rotation ownership is assigned.
- Host/volume encryption and least-privilege access are verified.
- Off-site upload and isolated restore are tested with the real provider.
- Alertmanager delivers a controlled alert to a staffed destination.
- RPO/RTO and incident contacts are approved.
- Privacy, consent, retention, and regulatory review for the target jurisdiction is complete.

Until every external gate is complete, the software is deployable but not approved for public clinical use.
