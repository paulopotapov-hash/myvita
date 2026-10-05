# P7-A deployment and rollback runbook

Status: **READY AS A PROCEDURE; EXECUTION BLOCKED BY EXTERNAL INFRASTRUCTURE**.

## Deploy

1. Approve the exact commit; require green CI/security review and record change/rollback owners.
2. Provision the qualified encrypted host, default-deny firewall, Docker/Compose and persistent volumes described in `p7-production-host.md`.
3. Configure private registry policy, publish the reviewed commit manually and record five image digests.
4. Create real DNS records and wait for authoritative resolution. Provision a publicly trusted renewable certificate. Self-signed certificates are test-only.
5. Inject runtime secrets from the approved manager. Use exact HTTPS CORS/trusted hosts and keep public registration disabled.
6. Configure private off-site backup and a staffed Alertmanager receiver; prove both before traffic.
7. Run `scripts/production_preflight.sh`. Render base, monitoring, TLS and registry overlays with `docker compose config --quiet`.
8. Pull digest-pinned images. Before migration, stop/quiesce application writes and create a checksum-verified backup with the currently deployed backup image; for a new empty database, record that this gate is not applicable. Abort if the backup fails. Then run the one-shot migration service and start remaining services with `--no-build`. Backend and scheduled backup are gated on migration success; backend health gates frontend/proxy. Compose startup alone does not create the required pre-migration backup.
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

`production_smoke.sh` verifies HTTPS, health/readiness, frontend, hidden metrics/OpenAPI and security headers. With approved synthetic credentials it verifies login, Secure+HttpOnly session cookie, authenticated identity and logout. Optional URLs must demonstrate a 403 authorization denial and 404 cross-tenant concealment. Database, monitoring targets, backup freshness and alert delivery remain operator-side checks because they are deliberately not public.

## Staging synthetic data and acceptance

Public onboarding/registration stay disabled, so staging identities are created with `backend/scripts/seed_staging.py` (two clinics: admin, doctor and patient each, plus a nurse in clinic A). It refuses to run unless `STAGING_SEED_CONFIRM=yes` and `STAGING_SEED_PASSWORD` are set, and refuses databases that contain non-seed clinics. The password is generated per environment and never stored in Git:

```sh
docker compose -f docker-compose.prod.yml exec -T -e STAGING_SEED_CONFIRM=yes \
  -e STAGING_SEED_PASSWORD="$STAGING_SEED_PASSWORD" backend python -m scripts.seed_staging
BASE_URL=https://<approved-host> SEED_PASSWORD="$STAGING_SEED_PASSWORD" node scripts/staging_acceptance.mjs
```

`staging_acceptance.mjs` is re-runnable and uses fewer than 10 logins so it stays inside the login rate limit. It covers SPA refresh, health, cookies, CSRF, the clinical write paths, role denials, cross-clinic concealment and logout revocation. The topology can be rehearsed locally with `docker-compose.prod.yml` plus `docker-compose.prod-http.yml` (see README); that rehearsal proves routing, port exposure and persistence but not TLS, HSTS, `Secure` cookies or JSON production logs.
