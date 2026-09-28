# P5 — Controlled Clinical Pilot Preparation

- Date: 2026-09-28
- Baseline: `p4.1-authorization-hardening` at `c5ceff9`
- Branch: `p5-controlled-clinical-pilot`
- Data: synthetic and temporary only

## 1. Executive summary

P5 produced a reproducible pilot definition, onboarding/runbook, access matrix, secrets inventory, backup/restore plan, monitoring/alerting plan, deployment readiness guide, incident response and privacy decision checklist. An isolated production-topology dry-run exercised migrations, application images, invitations, authorization, audit, backups, restore and monitoring. Its containers, volumes and synthetic databases were removed.

The application remains technically suitable for a controlled pilot. A real clinical pilot is not approved because production infrastructure, off-site recovery, human alert delivery and organizational/privacy gates do not exist as verified evidence.

## 2. Current architecture

Single-host Docker topology: reverse proxy is the only public component; static frontend and FastAPI backend share the proxy origin; PostgreSQL is on an internal network; a one-shot Alembic service gates backend startup; backup service writes validated dumps/checksums; monitoring comprises Prometheus, Grafana, Alertmanager, metrics proxy and database/host/container/blackbox exporters. Production backend is read-only, drops capabilities and uses secure cookies. Real TLS/domain and providers are external inputs.

## 3–4. Pilot scope and access matrix

The proposed configurable cohort and included/excluded workflows are in `first-clinical-pilot.md`. `pilot-access-matrix.md` mirrors P4.1: patient own access, doctor/nurse clinical access, administrative operational-only data, patient-only consent mutation and strict tenant isolation.

## 5. Onboarding procedure

`clinic-onboarding.md` and `pilot-runbook.md` cover supervised first-clinic bootstrap, immediate closure of public onboarding, staff/patient invitation, private token delivery, acceptance/password/session, audit verification, deactivation and revocation. No permanent superadmin is introduced.

## 6. Account security

Password change requires the current password, changes the Argon2id hash, increments token epoch and issues a fresh current session. Logout/deactivation revoke captured sessions. Password recovery, MFA, reactivation and role changes are absent. Recovery must be a controlled, approved identity-verification escalation; no password may be emailed. **MFA REQUIRED BEFORE PRODUCTION CLINICAL USE.**

## 7. Invitation flow

Staff invitations are clinic-admin-only; patient invitations are clinic-admin or doctor/nurse. Tokens are high entropy, digest-only at rest, expiring, replacement-revocable, tenant/role bound, row-locked and single use. The dry-run proved doctor/patient acceptance (200), replay (410), invalid token (404), expired token (410) and post-deactivation session rejection (401).

## 8–14. Operational controls

- Secrets: `pilot-secrets.md`; external approved store/rotation owners blocked.
- Database/backups: `pilot-backup-restore.md`; local tooling ready, real off-site evidence blocked.
- Monitoring: `pilot-monitoring.md`; topology/rules ready, human receiver pending.
- HTTPS/domain: `pilot-deployment.md`; no DNS/certificate/host was purchased or deployed.
- Incident response: `pilot-incident-response.md`; named owners/legal timelines pending.
- Privacy: `pilot-data-protection-checklist.md`; no legal-compliance claim; decisions remain blocked.

Development/test/production separation is explicit. Logs and application metrics were scanned during the dry-run; no tested credentials/tokens/cookies appeared, and application metrics contained no patient/clinic/user/clinical labels. Browser session state remains HttpOnly-cookie based and frontend query cache is identity-scoped/cleared by existing tests.

## 15. Dry-run results

An isolated Compose project used production, local-HTTP and monitoring overlays with separate ports, networks and named volumes. Evidence:

| Step | Result |
|---|---|
| Six local images / infrastructure startup | PASS |
| PostgreSQL health and migration service | PASS |
| Backend/frontend/proxy health/readiness | PASS |
| Clinic/admin bootstrap with synthetic identity | PASS |
| Doctor invite/accept/session | PASS |
| Patient invite/accept/own access | PASS |
| Consent own grant | 201 |
| Administrative clinical-detail attempt | 403 |
| Cross-tenant patient attempt | 404 |
| Replay / invalid / expired invitations | 410 / 404 / 410 |
| Logout and deactivation session revocation | 401 |
| Audit persistence | 13 rows observed |
| Local backup/checksum/freshness | PASS |
| Restore into isolated database | PASS; restore target removed |
| Prometheus config / rules | PASS; 15 rules |
| Prometheus targets | 8 healthy targets |
| Grafana health | PASS |
| Logs/metrics sensitive-data scan | PASS |
| Teardown | containers, networks, volumes and synthetic databases removed |

The Alertmanager receiver intentionally had no external integration; no claim of human delivery is made.

## 16. Security test results

The 113-test backend suite covers cross-tenant/IDOR, role escalation, replay/expiry, session/password revocation, unauthorized patient/admin clinical access, mass assignment, CSRF, CORS/origin, Host validation, rate limiting and safe error behavior. P5 repeated representative live 401/403/404 paths. Gitleaks uses two narrow prose-only exceptions and no path/file-wide suppression.

## 17–19. Gate requirements, blockers and owners

| Requirement | Status | Evidence | Owner |
|---|---|---|---|
| Authentication/password/session invalidation | READY | backend suite + dry-run | application/security |
| P4.1 RBAC and tenant isolation | READY | 113 tests + live 403/404 | application/security |
| Invitations/onboarding mechanics | READY | tests + live accept/replay/expiry | clinic/application |
| Audit capture | READY | tests + 13 dry-run events | security/operations |
| Local backup and isolated restore tooling | READY | checksum and restore dry-run | backup owner |
| Production domain/TLS/encrypted host | BLOCKED | no external infrastructure | infrastructure |
| Production secret manager/rotation | BLOCKED | inventory only | security/infrastructure |
| Real immutable off-site backup/restore | BLOCKED | local evidence only | backup/infrastructure |
| Monitoring topology/rules | READY | config, 15 rules, 8 targets | monitoring |
| Staffed alert destination | CONFIGURATION REQUIRED | placeholder receiver only | operations/on-call |
| MFA/password recovery | BLOCKED | not implemented/provider absent | product/security/identity |
| Operational owner/support rota | BLOCKED | must be named | clinic/operations |
| Incident procedure | CONFIGURATION REQUIRED | generic runbook; contacts absent | incident/privacy |
| Privacy/legal basis/DPIA/contracts/retention | BLOCKED | decision checklist only | controller/legal/privacy |
| Public deployment | NOT APPLICABLE | explicitly outside P5 | — |

## 20–21. Pilot gates

**TECHNICAL PILOT READY: YES**

The reviewed code and reproducible local production topology pass the technical dry-run without a new P0/P1 blocker.

**CLINICAL PILOT READY: NO**

Real clinical processing remains blocked until the infrastructure, recovery, alerting, ownership and privacy/legal rows above are closed with evidence.

## 22. Exact next actions

1. Name clinic, operational/on-call, security, backup, incident and privacy owners.
2. Approve controller/processor model, purpose/legal basis, DPIA, notices, contracts, retention/deletion and incident-notification process.
3. Provision encrypted private infrastructure, DNS/TLS and an approved secret manager.
4. Configure unique production secrets, exact trusted hosts/CORS and a private invitation-delivery channel.
5. Provision immutable encrypted off-site storage; prove upload and timed isolated restore.
6. Configure a staffed Alertmanager receiver; prove firing and resolved delivery.
7. Approve cohort/roles/support capacity and execute the pre-pilot checklist on the reviewed release.
8. Do not admit real data until the Clinical Pilot Gate is re-reviewed as YES.
