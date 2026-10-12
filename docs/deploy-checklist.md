# Deploy checklist (mandatory)

Run this checklist before and after **every** deploy that is reachable from the internet: production, staging, demos and pilots. It complements `p7-deployment-runbook.md` (the full procedure) and does not replace it. Every box must be ticked or explicitly marked "not applicable" with a reason, and the record kept with the change.

Never paste secret values, real credentials or clinical data into this checklist, a ticket or a chat. Check that values are set and well-formed; do not print them.

## 1. Before the deploy

### Code and tests
- [ ] The exact commit to deploy is approved, and CI on that commit is green: lint, types, tests, migrations up/down, security scans, image builds.
- [ ] The working tree used for the build is clean (`git status`), and the image digests to deploy are recorded.
- [ ] The migrations this deploy will apply are listed: `alembic history -r current:head` against a copy, or the files in `backend/migrations/versions/` since the deployed revision. Each one has been read, and its downgrade behaviour is known. Several migrations refuse to downgrade while new data exists (clinical history `a0b1c2d3e4f5`, medication start date `5f3a9c1e7b2d`). Rollback is therefore a forward fix or a restore, never an assumed downgrade.

### Configuration and secrets (values never printed)
- [ ] `scripts/production_preflight.sh` passes with the environment that will run. It refuses missing or placeholder secrets, a local domain, CORS without explicit HTTPS origins, wildcard hosts, short or reused keys, and a runtime DB role equal to the owner.
- [ ] `ENVIRONMENT=production` for production. Staging uses `ENVIRONMENT=staging`, never `development`.
- [ ] `DEBUG=false`, `COOKIE_SECURE=true`, and `CORS_ORIGINS` and `ALLOWED_HOSTS` list only the approved HTTPS origins and hosts.
- [ ] `MFA_REQUIRED_FOR_STAFF=true`, and `MFA_ENCRYPTION_KEY` and `PRIVACY_FINGERPRINT_KEY` are set and distinct.
- [ ] No development setting is in use: no `.env` copied from a laptop, public patient registration and clinic onboarding only if explicitly approved, and `ALLOW_DIRECT_STAFF_CREATION=false`.

### MFA dev/demo bypass (see `p6-mfa-password-recovery.md`)
- [ ] `MFA_DEV_BYPASS_EMAILS` is **empty**. Production refuses to start otherwise.
- [ ] If an online staging or demo deliberately keeps it, `MFA_DEV_BYPASS_CODE` is replaced. The default `123456` is public. The new code must not be shared outside the people who use those accounts.
- [ ] After start-up, the backend log has **no** `MFA dev bypass is ACTIVE` warning, unless a staging bypass was deliberately approved. The warning never shows the code or the emails.

### Backup
- [ ] Application writes are stopped or quiesced, and a backup was taken just before migrating (`scripts/backup_db.sh`; documents with `scripts/backup_documents.sh`).
- [ ] The backup is checksum-verified (`scripts/check_backup.sh`), and the latest restore drill succeeded (`scripts/verify_restore.sh <dump> --alembic-image <backend image>`). If the backup fails, **stop**: do not migrate.

### Rate limiting and processes
- [ ] The backend runs **one** process (the image starts a single `uvicorn` with no `--workers`). Rate-limit counters live in that process's memory.
- [ ] If this deploy runs **more than one** backend process or replica (uvicorn/gunicorn workers, or several containers), Redis must be configured for rate limiting **before** it goes live. Otherwise every process keeps its own counters, so limits multiply by the number of processes and the per-account login limit stops being reliable. This is not configured today. The switch is the `RATE_LIMIT_STORAGE_URI` setting, but it needs a Redis service, the `redis` package and a test: follow `docs/rate-limiting.md`. Do not mark it done unless it was actually configured and tested.

## 2. Migrate, then provision the runtime role

- [ ] Run migrations as the **schema owner**, never as the runtime role. With the production compose file, the one-shot `migrate` service runs `alembic upgrade head && python -m app.db_provisioning`. Run it and check that it exits 0.
- [ ] If migrations are run by hand instead, run the provisioning **immediately after**, as the owner:
  `MIGRATION_DATABASE_URL=<owner URL> APP_DB_ROLE=<runtime role> APP_DB_PASSWORD=<runtime password> python -m app.db_provisioning`
  (from `backend/`; inject the values from the secret store, never type them on a shared screen). Provisioning is idempotent. It refuses a role equal to the owner, and a role with elevated attributes.
  Without this step, the new tables and columns keep the default grants, and the runtime role could DELETE medication or rewrite clinical history revisions.
- [ ] Confirm the runtime role has only what the app needs. Run `backend/tests/test_db_privileges.py` against a staging copy, or check `has_table_privilege` / `has_column_privilege` for at least these:
  - `medications`, `clinical_history_entries`: no DELETE;
  - `clinical_history_revisions`, `medical_record_revisions`, `audit_logs`, `documents`, `reminder_deliveries`: no UPDATE or DELETE;
  - `waitlist_entries`, `waitlist_offers`, `appointment_requests`: no DELETE, UPDATE only on their status columns;
  - no DDL.

## 3. After the deploy

- [ ] `GET /health` and `GET /ready` return 200 (`/ready` also checks the database).
- [ ] `scripts/production_smoke.sh` passes with `SMOKE_BASE_URL` set to the HTTPS origin. Use approved **synthetic** smoke credentials (`SMOKE_EMAIL`/`SMOKE_PASSWORD`, plus `SMOKE_TOTP_SECRET` or `SMOKE_MFA_CODE`). It checks HTTPS, security headers, hidden metrics and OpenAPI, login with MFA, the session cookie and logout.
- [ ] Authentication, CSRF and authorization still work. Use a synthetic patient and a synthetic doctor:
  - a write without the CSRF header gets 403;
  - the patient cannot open `/app` pages;
  - the doctor cannot see a patient outside their care team.
- [ ] The backend log shows no startup error and no `MFA dev bypass is ACTIVE` warning (see above). Alerts and monitoring report the new version as healthy.
- [ ] The off-site backup job ran after the deploy, or is scheduled for the next window.
- [ ] The scheduling `jobs` service is running (`docker compose -f docker-compose.prod.yml ps jobs`), and its log shows a `scheduling_jobs reminders=… expired_offers=… closed_entries=…` line every minute (counts only). Without it, no appointment reminder is sent and waiting-list offers never expire. More than one replica is safe: a database lock lets one pass run at a time.
- [ ] Reminders go out **in the app only**. E-mail and SMS reminders are prepared in the data model but switched off: there is no sender for them, and turning them on needs its own review (transactional e-mail never carries clinical information, `docs/email-delivery.md`).

## 4. When to stop, and how to roll back

Stop the deploy, and keep or restore the previous version, if any of these happens:
- preflight fails;
- the pre-migration backup fails;
- a migration fails or is refused;
- provisioning fails;
- `/ready` stays down;
- the smoke test fails;
- authorization or CSRF checks fail;
- the bypass warning appears where it was not approved.

Follow "Rollback" in `p7-deployment-runbook.md`:
- **Application or configuration problem:** remove traffic, redeploy the previous reviewed image digest and configuration, re-run preflight and smoke, then restore traffic.
- **Migration problem:** do not assume `alembic downgrade` is safe, because several migrations refuse to downgrade while new data exists, by design. Prefer a forward fix.
- **Database restore:** only for confirmed corruption or data loss, under incident command, from a checksum-verified backup restored **first in isolation** (`scripts/verify_restore.sh`). It may lose data up to the RPO and needs a privacy and clinical impact assessment.

Never run destructive SQL against production (`DROP`, `TRUNCATE`, mass `DELETE`/`UPDATE`) to "fix" a deploy. Preserve logs, backups and timelines, and rotate any credential that may have been exposed.
