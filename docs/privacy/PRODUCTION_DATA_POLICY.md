# Production-data policy and environment separation

## Rule

**Production clinical data must not be copied into development, test, staging, CI or any developer machine by default.** All development, tests, demos, screenshots, documentation examples and acceptance runs use synthetic data. Real personal data must never appear in source control, CI artifacts, debug fixtures or documentation.

## Evidence this is already how the project works

- Tests use `*.example` addresses and generated passwords; the shared test world lives only in a throwaway database (`backend/tests/phase1_world.py`).
- Staging seed identities are created by `backend/scripts/seed_staging.py`, which needs `STAGING_SEED_CONFIRM=yes`, takes the password from the environment and refuses a database containing non-seed clinics.
- `.env` files, dumps, `*.sql` and backups are git-ignored; gitleaks is configured.
- Documentation examples in this repository contain only synthetic identifiers.

## Exceptions (production-derived data for debugging)

Only when no synthetic reproduction is possible:

1. Written approval from the controller (clinic) for the specific purpose and time window.
2. Minimise: the smallest set of rows and columns; prefer ids and shapes over content.
3. Anonymise or pseudonymise before it leaves production (replace names, emails, phone, birth date, national health number, free-text clinical fields).
4. Work only in an isolated, access-controlled environment with named participants; no personal devices, no shared chat, no tickets containing content.
5. Delete the copy and its backups when the work ends; record who, what, when, and the deletion.
6. Record the exception in the incident or change ticket.

Restores of production backups for disaster-recovery drills fall under this rule: use the isolated procedure in `docs/operations.md` and destroy the temporary instance.

## Environment separation requirements

| Requirement | State |
|---|---|
| Separate databases, credentials, secrets, domains per environment | Required by production compose (no defaults for secrets, explicit hosts/origins). Dev uses static credentials and must not be network-exposed with real data |
| Staging cannot reach production | No production credential or address exists in the repository; enforce with separate hosts/networks and distinct secrets when infrastructure is created **[to verify on real infrastructure]** |
| Different secrets per environment | Required; `JWT_SECRET_KEY` shared across environments would let a staging token pass in production |
| Separate backup destinations | Required: staging must not write to the production bucket; use different prefixes and credentials |
| Production features gated | `ENVIRONMENT=production` enforces secure cookies, no wildcard hosts/origins, no local hosts, strong secrets, no direct staff creation, disabled `/docs` |

## Secure development lifecycle (summary)

| Control | Evidence |
|---|---|
| CI gates | Ruff, `mypy app`, pytest, migrations up/down/up, frontend typecheck/lint/test/build, `pip-audit`, `npm audit`, production preflight (`.github/workflows/ci.yml`) |
| Security regression tests | `test_phase1_security.py` (auth, CSRF, RBAC matrix, tenant/patient IDOR, audit, errors) and `test_privacy_controls.py` |
| Migrations | Alembic, one head, upgrade/downgrade checked in CI |
| Dependency hygiene | Dependabot PRs present; `SECURITY-EXCEPTIONS.md` empty |
| Secrets | Not in Git; production compose requires them at start |
| Gaps | Mandatory review rule not evidenced; no container image scan; no automated staging deploy; no external penetration test; MFA/password recovery missing |
