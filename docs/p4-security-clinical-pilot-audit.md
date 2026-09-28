# P4 — Security & Clinical Pilot Audit

- Audit date: 2026-09-27
- Baseline: `p3-production-readiness` at `e08de01`
- Audit branch: `p4-security-clinical-pilot-audit`

## Executive Summary

The P3 baseline was reproducible: 105 backend tests and 35 frontend tests passed before P4 changes. Production Compose has a sound single-host topology, authentication and tenant filters are materially stronger than a typical prototype, and no exploitable SQL/command/path/SSRF surface was found in the application code.

The audit did not accept the previous broad “READY” labels at face value. It found that direct staff creation could bypass the invitation model, invitation bearer tokens were placed in URLs, no tenant administrator offboarding API existed, and sensitive public endpoints were not throttled. Those findings were corrected and regression-tested. The three known warnings were removed at their source rather than filtered.

Two authorization-policy questions remain unresolved: non-clinical administrative roles currently receive patient demographic/appointment data, and any non-patient user in the clinic can operate consent endpoints. Until the clinic defines the minimum necessary access and consent-recording authority, the backend cannot prove least privilege. This is a security/pilot blocker, not a frontend issue.

**TECHNICALLY READY FOR CONTROLLED PILOT: NO**

The code is materially closer, but the gate remains closed until the RBAC/consent policy is decided and enforced, and a private pilot environment supplies TLS, managed secrets, verified off-site restore, human alert delivery, and approved clinical/privacy processes.

## Scope and Methodology

Reviewed all backend routes, services, request/response schemas, models, migrations, frontend auth/cache flows, Dockerfiles, development/production/monitoring Compose, proxy configuration, backup scripts, CI and operational documentation. Tests exercised authentication, stale/replayed sessions, invitations, cross-tenant identifiers, malformed input, CSRF, role denial, deactivation, migrations and production topology.

Static and supply-chain checks: Ruff, MyPy, Bandit, pip-audit, npm audit and full-history Gitleaks. Infrastructure checks: five Docker builds, Compose rendering, Prometheus configuration and alert rule tests, container health/readiness, public registration closure and untrusted Host rejection.

No real clinical data was used. Automated data was synthetic and confined to disposable databases/volumes.

## Findings

### P4-001 — Direct staff creation bypassed invitation acceptance

- Severity: P1
- Component: authentication/onboarding
- Evidence: authenticated `POST /api/v1/staff` accepted an administrator-selected initial password while the production UI used invitations.
- Impact: staff could receive shared/operator-known passwords and accounts could be activated without bearer-token acceptance.
- Reproduction: clinic admin submits the legacy `StaffCreateRequest` directly.
- Correction: direct creation now defaults off, production refuses to start if enabled, and the endpoint returns 403 unless the explicit test/development escape hatch is enabled.
- Status: FIXED; regression test confirms no user is created.

### P4-002 — Invitation bearer token appeared in URL query parameters

- Severity: P1
- Component: invitations/frontend
- Evidence: `/convite?token=...` and `GET /invitations/preview?token=...`.
- Impact: tokens could enter browser history and logging/analytics layers outside the repository’s query-stripping logger.
- Correction: links use a URL fragment, the fragment is immediately removed with `history.replaceState`, and preview is POST-only with the token in the JSON body. GET preview now returns 405.
- Status: FIXED; valid/tampered/query-string regression tests added.

### P4-003 — No application-level account offboarding

- Severity: P1
- Component: account lifecycle
- Evidence: `is_active` and `token_epoch` existed but no route could disable a staff/patient account.
- Impact: a compromised or departed user retained access until direct database intervention.
- Correction: tenant-scoped clinic-admin deactivation endpoints preserve records, set `is_active=false`, increment `token_epoch`, audit `USER_DISABLED`, reject cross-tenant IDs as 404, and prevent staff self-deactivation.
- Status: FIXED; stale-session and cross-tenant tests added. Reactivation and role changes remain deliberate gaps.

### P4-004 — Invitation/password security endpoints lacked explicit throttling

- Severity: P2
- Component: API abuse resistance
- Evidence: invite create/preview/accept and password change had no decorator-based limit.
- Impact: avoidable request amplification and increased blast radius for a compromised session/IP.
- Correction: authenticated invitation/password writes use 20/minute; unauthenticated preview/accept use 10/minute per trusted client IP.
- Status: FIXED. Multi-replica deployments still require shared limiter storage.

### P4-005 — Deprecated test and password libraries produced warnings

- Severity: P2
- Component: dependencies/tests
- Evidence: Starlette requested `httpx2`; Passlib read deprecated `argon2.__version__`; one test passed cookies per request.
- Impact: future upgrades could break the test harness or password backend; warnings obscured new regressions.
- Correction: tests use `httpx2`; password hashing uses maintained `argon2-cffi` directly and verifies existing standard Argon2id hashes; the test uses the client cookie jar.
- Status: FIXED; 109 backend tests pass with zero warnings.

### P4-006 — Gitleaks false positive made the blocking scan fail

- Severity: P2
- Component: CI/security scan
- Evidence: prose in `docs/production-readiness.md` matched the generic API-key rule although it contained no assignment or secret.
- Impact: the advertised blocking security gate was red.
- Correction: narrow exact-phrase allowlist; no file/path-wide exception.
- Status: FIXED; full 44-commit history passes.

### P4-007 — Consent authority is broader than documented clinical access

- Severity: P1 — SECURITY BLOCKER
- Component: RBAC/consents
- Evidence: consent services special-case patients but allow every other same-clinic user, including `clinic_admin` and `staff_role=admin`, to list, grant and revoke. By contrast, medical records/medications explicitly require doctor/nurse.
- Impact: a non-clinical user may alter the recorded expression of patient consent.
- Correction: not changed without a product/clinical/legal decision defining whether only the patient, doctor/nurse, or a verified administrative witness may record each consent type.
- Status: OPEN.

### P4-008 — Patient/appointment data minimization by administrative role is undefined

- Severity: P1 — SECURITY BLOCKER
- Component: RBAC/data exposure
- Evidence: clinic admins and all staff subroles can list full patient birth date/phone/health number, read/update patient details, and read all clinic appointments including reason. Clinical-record and medication services are narrower.
- Impact: non-clinical roles may receive more personal/health-related data than necessary.
- Correction: requires a field-by-field role matrix and an operational scheduling model; hiding UI elements would not fix the backend exposure.
- Status: OPEN.

### P4-009 — Recovery, MFA and account reactivation are absent

- Severity: P2
- Component: account lifecycle
- Evidence: authenticated password change exists; no verified recovery, MFA or reactivation workflow exists.
- Impact: lockout needs controlled support; stolen credentials rely on detection/deactivation/password change.
- Status: BLOCKED by identity/delivery provider and approved support policy. Do not implement an email-less reset shortcut.

### P4-010 — Database tenant invariants are only partially enforced in SQL

- Severity: P2
- Component: database defense in depth
- Evidence: medications use a composite patient/clinic FK; appointments, records, notifications and staff/user clinic consistency largely rely on service-layer checks.
- Impact: a future buggy migration/background task could create cross-tenant inconsistent rows even though current API tests block IDOR.
- Status: OPEN; introduce composite constraints through reviewed migrations before adding non-API writers.

### P4-011 — Development Compose binds services to all host interfaces

- Severity: P3
- Component: local development
- Evidence: development ports use host-wide bindings; production exposes only the proxy.
- Impact: a developer on an untrusted network may expose dev PostgreSQL/API/Vite.
- Status: OPEN. The file had a pre-existing uncommitted user port change and was deliberately not overwritten; bind development ports to `127.0.0.1` after reconciling that local change.

## Endpoint / RBAC Summary

| Resource | Patient | Doctor/Nurse | Administrative staff | Clinic admin | Anonymous |
|---|---|---|---|---|---|
| Session/password | own | own | own | own | login only |
| Patient directory | denied | same clinic | same clinic | same clinic | denied |
| Patient detail/update | own record | same clinic | same clinic | same clinic | denied |
| Appointments | own | same clinic; mutate | same clinic; mutate | same clinic; mutate | denied |
| Medical records | own read | same clinic read/write | denied | denied | denied |
| Medications | own read | same clinic read/write | denied | denied | denied |
| Consents | own read/grant/revoke | same clinic | same clinic | same clinic | denied |
| Staff invitations | denied | denied | denied | create | accept with bearer token |
| Patient invitations | denied | create | denied by clinical-staff check | create | accept with bearer token |
| Staff/patient deactivation | denied | denied | denied | same clinic | denied |
| Audit history | no API | no API | no API | no API | denied |

Every protected row lookup tested for cross-tenant access returns denial/404 from the backend. The table also shows why P4-007/P4-008 need an explicit policy decision.

## Security Matrix

| Area | Assessment |
|---|---|
| Authentication | Strong baseline: constant-work unknown-user login, Argon2id, generic failures and throttling. |
| Sessions/JWT | HttpOnly cookie, required claims/algorithm, expiry, active-user and epoch validation. Simultaneous sessions intentionally share the epoch. |
| Logout/password change/offboarding | All increment epoch; captured old tokens fail. |
| CSRF/CORS | Signed session-bound double-submit token plus Origin validation and explicit CORS lists. |
| Cookies | Secure/SameSite/HttpOnly controls; production rejects insecure cookies. |
| RBAC | Enforced server-side, but consent/demographic administrative scope is unresolved. |
| Multi-tenancy/IDOR | Strong service filters and negative tests across clinical resources, invitations, notifications and offboarding. Database defense in depth is incomplete. |
| Invitations | 384-bit random token, SHA-256 at rest, expiry, row lock, role/tenant binding, single use, replacement revocation, throttling and no URL query token. |
| API validation | Unknown fields rejected, bounded bodies/pagination, typed UUID/enums; ORM-bound queries prevent SQL injection. No shell/network/user path execution exists. |
| Errors/logging | Generic 500/503, no SQL/bodies/query strings/tokens; request IDs and no-store API responses. |
| Frontend | Session token never enters JS storage; tenant cache clears across identity/logout/401; protected routes are UX only, backend remains authoritative. |
| Docker/network | Production publishes proxy only; internal data network, read-only backend, capability drop and non-root images where practical. Monitoring cAdvisor privilege is documented. |
| Secrets/dependencies | Required production secrets fail closed; audits pass. Real secret manager/rotation and image provenance remain deployment gates. |
| Backups | Atomic/checksummed local and S3-compatible tooling; real encrypted/immutable provider and restore evidence absent. |
| Monitoring/alerting | Rules/dashboard validate; no staffed destination or real delivery test. |

## Clinical Pilot Matrix

| Item | Classification | Requirement |
|---|---|---|
| Initial clinic/first admin | CLINICAL PROCESS GAP | Verified identity, contract and supervised bootstrap. |
| Doctor/nurse/patient invitation | READY | Secure technical flow; configure approved private delivery channel. |
| Password change/session revocation | READY | Tested. |
| Password recovery/MFA | BLOCKED | Verified identity/email provider and policy. |
| Offboarding | READY | Deactivation/revocation exists; clinic must assign authority and response time. |
| Role changes/reactivation | CLINICAL PROCESS GAP | Define approval; no application workflow yet. |
| Consent and admin access | SECURITY BLOCKER | Decide and enforce least-privilege matrix before pilot. |
| Audit capture | READY | Events persist independently; no clinic-facing review/export workflow. |
| Local backup/restore | READY | Scripts and disposable validation exist. |
| Off-site recovery | BLOCKED | Real provider, credentials, immutability and restore drill. |
| Monitoring | CONFIGURATION REQUIRED | Deploy stack and set retention. |
| Human alerts/support | BLOCKED | Staffed destination, contacts and escalation rota. |
| Retention/deletion | CLINICAL PROCESS GAP | Legal basis, retention periods, deletion/restriction procedure. |
| Privacy/DPIA | BLOCKED | Controller/processor roles, DPIA and jurisdictional approval. |

## First Pilot Threat Model

| Threat | Impact | Existing mitigation/test | Gap | Priority |
|---|---|---|---|---|
| Compromised patient | Own-data exposure, abusive requests | own-patient scoping, CSRF, throttled login, epoch | detection/support process | P2 |
| Compromised staff | broad clinic clinical access | clinical role checks, audit, deactivation | least-privilege assignment/review | P1 |
| Stolen credentials | account takeover | Argon2id, generic login, rate limit, password change/deactivation | MFA/detection | P1 |
| Stolen invitation | account activation | high entropy, expiry, replacement revocation, one use, HTTPS requirement | approved delivery channel | P1 |
| Cross-clinic attacker | clinical data breach | tenant-derived filters and extensive IDOR tests | composite DB constraints | P1/P2 |
| IDOR | arbitrary record access | UUIDs never authorize; clinic/owner filters | keep endpoint inventory tests current | P1 |
| Stolen session | temporary/full account access | Secure HttpOnly cookie, CSRF, expiry, epoch revocation | MFA/device/session inventory | P1 |
| Brute force | takeover/DoS | constant-work login and per-IP limits | shared limiter for multiple replicas | P2 |
| API abuse | resource exhaustion | 1 MiB body cap, pagination, limits | global/edge limits and capacity test | P2 |
| Misconfiguration | insecure exposure | fail-closed production validators/Compose | deployment review and secret manager | P1 |
| Compromised backup | full data disclosure | checksums, private-network job, provider SSE option | real encryption/immutability/access test | P1 |
| Log exposure | identifiers/security metadata | no bodies/query strings/secrets/clinical payloads | central log ACL/retention | P1 |
| Frontend exposure | cached tenant data/token leakage | no session storage, cache clear, fragment removal, CSP/referrer policy | browser/device policy | P2 |
| Infrastructure failure | downtime/data loss | health/readiness, backups, alerts | real HA/provider/restore/alert exercise | P1 |

## Remaining Risks and Explicit Gate

Before reopening the gate:

1. Approve and implement the administrative/clinical RBAC and consent authority matrix (P4-007/P4-008).
2. Build a private pilot environment with real TLS, secret management and encrypted storage.
3. Prove real off-site upload and isolated restore; prove alerts reach a staffed human.
4. Define password recovery, invitation delivery, reactivation/role-change, incident, retention/deletion and support processes.
5. Complete DPIA/privacy/legal approval and assign clinic/controller responsibilities.

Until these are evidenced, **TECHNICALLY READY FOR CONTROLLED PILOT: NO**.
