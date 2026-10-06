# P7-A deployment and rollback runbook

Status: **READY AS A PROCEDURE; EXECUTION BLOCKED BY EXTERNAL INFRASTRUCTURE**.

## Deploy

1. Approve the exact commit; require green CI/security review and record change/rollback owners.
2. Provision the qualified encrypted host, default-deny firewall, Docker/Compose and persistent volumes described in `p7-production-host.md`.
3. Configure private registry policy, publish the reviewed commit manually and record five image digests.
4. Create real DNS records and wait for authoritative resolution. Provision a publicly trusted renewable certificate. Self-signed certificates are test-only.
5. Inject runtime secrets from the approved manager, including `APP_DB_ROLE`/`APP_DB_PASSWORD` (runtime database role, distinct from the owner `POSTGRES_USER`), `MFA_ENCRYPTION_KEY` and `PRIVACY_FINGERPRINT_KEY` (see `p7-secret-management.md` and `security/account-lifecycle.md#configuration`). Use exact HTTPS CORS/trusted hosts and keep public registration disabled.
6. Configure private off-site backup and a staffed Alertmanager receiver; prove both before traffic.
7. Run `scripts/production_preflight.sh`. Render base, monitoring, TLS and registry overlays with `docker compose config --quiet`.
8. Pull digest-pinned images. Start PostgreSQL, run the one-shot migration service, then start remaining services with `--no-build`. Backend and backup are gated on migration success. The migrate service runs as the schema owner: `alembic upgrade head`, then `python -m app.db_provisioning`, which creates or updates the least-privilege runtime role. That role gets LOGIN only, DML on application tables, INSERT/SELECT only on `audit_logs`, SELECT on `alembic_version`, and no DDL. The backend connects only as that role. Provisioning is idempotent and refuses a role equal to the owner or one with elevated attributes. Its `ALTER ROLE … PASSWORD` statement must not be captured by server statement logging (`log_statement` must not be `ddl`/`all` during migrate).
   - Migration `f6a7b8c9d0e1` stops without changing anything if two accounts' e-mails differ only by letter case. Resolve those accounts manually (decide which is legitimate) and re-run.
   - After the first deploy with mandatory MFA, every staff member and clinic admin enrols TOTP at their next login. Brief clinic admins first: they recover staff from the *Contas* page, while clinic admins themselves are recovered by the operator (`security/account-lifecycle.md#clinic-admin-recovery-operator-procedure`).
9. Verify container health, `/health`, `/ready`, Prometheus targets, Grafana authentication, backup freshness and alert delivery.
10. Run `scripts/production_smoke.sh` against HTTPS. Use only approved synthetic accounts/resources and remove them through the approved application workflow.
11. Enable traffic only after the release owner signs every P7 checklist gate.

## DNS and TLS

**BLOCKED — REAL DOMAIN REQUIRED. BLOCKED — REAL TLS CERTIFICATE REQUIRED.** The public application needs one approved hostname (conceptually `app.example.pt`, never treated as real). Use A/AAAA for a fixed ingress address or CNAME only where the platform supports it. Keep TTL low during controlled cutover, then raise it after stability. DNS ownership, CAA choice and health-based routing are operator decisions.

The TLS overlay redirects port 80 to 443, supports TLS 1.2/1.3 and HSTS. Certificate/private-key mounts are read-only and external to Git. Validate chain, hostname, expiry, renewal, OCSP/platform behavior, HTTP redirect, HSTS, secure cookies and HTTPS blackbox checks before traffic.

## Rollback

- Application/configuration: remove traffic, restore the previous reviewed digest/config version, run preflight and smoke checks, then re-enable traffic.
- Migration: never assume `alembic downgrade` is safe. Prefer a forward fix for compatible schema changes. For destructive/incompatible changes, stop writes and follow the change-specific migration plan.
- Database restore: only for confirmed corruption/data loss under incident command, using a checksum-verified off-site backup restored first in isolation. This may lose data up to the RPO and requires privacy/clinical impact assessment.
- Preserve logs, backups and timelines; rotate suspected credentials and notify the named incident/privacy roles.

## Production smoke contract

`production_smoke.sh` verifies HTTPS, health/readiness, frontend, hidden metrics/OpenAPI and security headers. With approved synthetic credentials (`SMOKE_EMAIL`/`SMOKE_PASSWORD`) it verifies login, Secure+HttpOnly session cookie, authenticated identity and logout. It follows the Phase 1 auth contract (`security/account-lifecycle.md`):
- A `202` MFA challenge must issue no session, only a Secure/HttpOnly/SameSite=Strict challenge cookie scoped to `/api/v1/auth/mfa`. The script then verifies the second factor with `SMOKE_MFA_CODE` (a fresh code) or `SMOKE_TOTP_SECRET` (needs `oathtool` or `python3`), and stops with BLOCKED if neither is set.
- Staff and clinic admins must report MFA as mandatory.
- An account with a pending action (for example, staff not yet enrolled) only gets its account gate verified (`403` + `X-Account-Action-Required`), with a warning.
- `SMOKE_EXPECTED_ROLE` optionally pins the role.

Optional URLs must demonstrate a genuine 403 authorization denial (`SMOKE_FORBIDDEN_URL`, refused if the 403 came from the account gate) and 404 cross-tenant concealment (`SMOKE_CROSS_TENANT_URL`). Both require an account with no pending action. Use a patient synthetic account for plain-login runs, or an MFA-enrolled staff/admin account with its seed stored in the secret manager. Database, monitoring targets, backup freshness and alert delivery remain operator-side checks because they are deliberately not public.
