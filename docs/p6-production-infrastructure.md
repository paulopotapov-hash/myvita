# P6 — Production Infrastructure & Go-Live Preparation

- Date: 2026-09-28
- Baseline: P5 `02250d5`
- Branch: `p6-production-infrastructure`
- Scope: preparation and local simulation only; no public deployment or real clinical data

## 1. Executive summary

P6 hardened fail-closed production configuration, disabled all interactive/OpenAPI schema exposure in production, made PostgreSQL pooling configurable, added aggregate authorization-denial monitoring, introduced an executable production preflight and supplied a non-secret production environment template. Existing deployment, backup, restore and monitoring assets were reused rather than rebuilt.

The repository is technically prepared for an operator to provision a future environment, but no production environment exists. External infrastructure, real secrets/TLS/off-site recovery/human alerting and organizational/privacy approval remain blocking.

## 2. Initial/current state

| Area | Initial assessment | P6 result |
|---|---|---|
| Production Compose/images/private networks | READY | validated and simulated |
| Auth/RBAC/tenant isolation/audit | READY | unchanged; regression-tested |
| Production settings | PARTIALLY READY | strengthened against dev DB, weak signing material, HTTP CORS/local hosts |
| API documentation exposure | PARTIALLY READY | OpenAPI JSON now disabled with Swagger/ReDoc |
| Secret manager | BLOCKED BY EXTERNAL INFRASTRUCTURE | inventory/template/preflight ready |
| TLS/domain | PARTIALLY READY | proxy/overlay/checklist ready; real DNS/cert blocked |
| Local backup/restore | READY | revalidated |
| Off-site backup/restore | PARTIALLY READY | simulator/config ready; real provider blocked |
| Monitoring | READY | auth/authz signals added |
| Human alert delivery | MISSING / EXTERNAL | receiver remains intentionally unconfigured |
| MFA/recovery | MISSING / POST-P6 | architecture decision documented |
| Owners/privacy approval | BLOCKED | placeholders/checklists only |

## 3. Production architecture

Internet → firewall (443 only; optional 80 redirect) → TLS reverse proxy → static frontend and `/api` backend → internal PostgreSQL. Backend, frontend, database, Prometheus, Alertmanager and exporters have no public ports. Grafana binds to loopback for tunneled administration. A migration job gates backend startup; a backup service uses the data network and dedicated volumes; monitoring uses a separate internal network.

## 4. Configuration

Production forces `ENVIRONMENT=production`, `DEBUG=false`, secure cookies, explicit HTTPS CORS, explicit non-local trusted hosts, CSRF/origin validation, trusted proxy CIDR, private database URL, disabled direct staff creation and no Swagger/ReDoc/OpenAPI schema. Critical values fail closed. Database pool size, overflow and timeout are bounded/configurable. Frontend production API base remains same-origin, avoiding cross-origin cookie exposure.

## 5. Secret management

| Secret | Purpose | Required | Rotation | Where used |
|---|---|---|---|---|
| PostgreSQL credentials | DB authentication | yes | on compromise/periodic policy | db, backend, migration, backup, exporter |
| JWT signing material | session/CSRF signing | yes | scheduled and incident; invalidates sessions | backend/migration config |
| Metrics token | internal scrape authorization | with monitoring | scheduled/incident | backend + metrics proxy |
| Grafana admin password | dashboard administration | yes | bootstrap/incident | Grafana |
| S3/cloud credentials | off-site backup | for real pilot | short-lived/predefined | backup service only |
| Backup encryption/provider keys | confidentiality/immutability | yes | provider policy | provider/host, not app Git |
| TLS private key | HTTPS | yes | renewal/incident | proxy/platform only |
| SMTP/webhook/pager credential | alerts and future verified delivery | external | provider/incident | Alertmanager/delivery service |

`.env.production.example` contains placeholders only. `production_preflight.sh` rejects missing placeholders, local domains, wildcard hosts, non-HTTPS CORS and short signing keys before rendering Compose/rules. Production settings additionally reject obvious development/default credentials. Real values require an approved secret manager, access review and custodians.

## 6. TLS/domain

The TLS proxy template supports TLS 1.2/1.3, HSTS, HTTP→HTTPS redirect, secure cookies and security headers. Operator checklist: provision approved DNS; allow inbound 443 and optional redirect-only 80; deny database/backend/monitoring public access; mount certificate/private key read-only outside Git; configure renewal; use exact host/CORS; validate chain, renewal, Host rejection and proxy headers. No domain/certificate was purchased or issued.

## 7. Database

Alembic upgrade/check/downgrade/upgrade, PostgreSQL backups and isolated restore are validated. ORM queries are parameterized; transactions and pool pre-ping are present. Pool controls now expose bounded `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` and timeout. Production must use a dedicated non-superuser limited to the application schema; migration ownership/grants require the selected platform.

API tenant isolation is extensively tested. Composite patient/clinic protection exists for medication; appointments, records, notifications and staff/user clinic consistency still rely partly on service checks. This is a documented defense-in-depth improvement before non-API writers, not justification for an unreviewed P6 schema migration.

## 8. Backup/restore

Automatic schedule, configurable retention, atomic custom dumps, archive/checksum verification, failure metrics, S3-compatible upload, provider SSE option and isolated restore are implemented. Local and simulated off-site failure paths pass. Real bucket access policy, encryption/immutability, upload and timed restore evidence remain blocked. Proposed RPO 24h/RTO 4h require owner approval and measurement.

## 9–10. Monitoring and alerting

Prometheus/Grafana/Alertmanager, node/cAdvisor/PostgreSQL/blackbox exporters and backup metrics cover availability, latency/errors, database, resources, restarts and backup freshness. P6 adds aggregate authentication-failure and authorization-denial alerts; neither metric has user, clinic, resource or clinical labels. Alert annotations are operational only. Alertmanager has no real destination, so human receipt/resolution is blocked.

## 11. Logging and audit

- **Application logs:** request ID, method, path without query, status, duration, exception type only; JSON outside development.
- **Security logs:** generic login outcome by internal user ID where available; no submitted password/token/header/cookie.
- **Audit logs:** actor/tenant/action/result/resource identifiers and bounded metadata, stored independently; no API currently exposes the history.
- **Metrics:** aggregate bounded operational series only.

Proxy logs omit query strings and bodies. Retention/central log ACLs are external configuration. Clinical payloads, passwords, invitation/reset tokens, cookies and authorization headers must never be shipped. Critical events include login success/failure, password/logout/session revocation, invitations, permission/CSRF/rate-limit denial, clinical access/mutations and deactivation.

## 12. CI/CD

CI blocks on whitespace, Ruff, MyPy, tests/coverage, migration cycle, backup tests, pip/npm audits, Bandit medium/high, full-history Gitleaks, frontend checks, five Docker builds, monitoring config/rule tests, dashboard JSON and Compose rendering. P6 adds the production preflight. Deployment is deliberately absent. Future delivery requires immutable version tags/digests, SBOM/signing/provenance, protected environment approval, migration/backup gate, post-deploy smoke checks and rollback to a reviewed image.

## 13. MFA/recovery

`p6-mfa-password-recovery.md` selects WebAuthn/passkeys with reviewed TOTP fallback and a digest-only, single-use, expiring reset-token design. Provider, identity verification, delivery, policy and implementation are POST-P6 blockers. MFA remains required before production clinical use.

## 14. Operational ownership

`p6-operational-ownership.md` supplies owner/backup/escalation/procedure slots for infrastructure, DB, security, backup, monitoring, incidents, releases, secrets, privacy and clinical operations. All are placeholders and therefore blocked until named/tested.

## 15. Privacy/DPIA dependencies

Technical categories: identity/contact/demographic data, appointments/reasons, consents, records, medications, notifications, audit/security metadata. Browser → proxy → app → PostgreSQL is the primary flow; bounded metrics go to monitoring; verified dumps go to local/off-site backup. Access follows P4.1 roles and tenant filters; auditability exists.

Legal/organizational decisions remain human review: controller/processor roles, purpose/basis, DPIA, notices/consent language, retention/deletion/restriction/access requests, backup/log retention implications, incident notification, subprocessors/data locations, DPA/contracts and clinic responsibilities. No compliance claim is made.

## 16. Production simulation

P6 used the isolated `myvita-p6-sim` Compose project with synthetic values/data, migrations, backend/frontend/proxy, monitoring, backup, restore and smoke/security checks. The first run exposed and fixed three production-only integration defects: the backend healthcheck used a rejected `Host`, the metrics/Blackbox path used an untrusted internal host, and the startup backup raced migrations. A second clean-volume boot proved the corrected ordering and restored the automatic startup dump at Alembic revision `e5f6a7b8c9d0`. TLS 1.2/1.3 configuration was syntax-validated with a disposable self-signed certificate; no public certificate was issued. All simulation containers, networks, volumes and disposable databases were removed afterward without touching existing development volumes.

## 17. Go-live checklist

See `p6-go-live-checklist.md` for the A–L PASS/PARTIAL/BLOCKED matrix. `scripts/production_preflight.sh` is the executable configuration subset; it cannot prove external ownership, TLS, backups, alerts or legal approval.

## 18. Remaining blockers

1. Real encrypted host/network/firewall and image registry/provenance.
2. DNS, renewable certificate and external HTTPS verification.
3. Approved secret manager, generated credentials, rotation and custodians.
4. Real encrypted immutable off-site backup and timed isolated restore.
5. Staffed alert receiver and exercised escalation.
6. MFA/password recovery provider, policy and implementation.
7. Named owners/on-call/support and incident exercise.
8. DPIA/privacy/legal/retention/contracts and clinical governance approval.

## 19. Validation results

- Backend: 119 tests passed; 95% statement coverage.
- Frontend: 35 tests passed across 11 files; lint, TypeScript and Vite production build passed.
- Static/security: Ruff, MyPy (67 files), Bandit medium/high, `pip-audit`, `npm audit`, Gitleaks and `git diff --check` passed.
- Data protection: Alembic upgrade/downgrade/upgrade/check passed on disposable PostgreSQL; local/off-site script tests passed; cold-start automatic dump restored at the current revision.
- Runtime: all production and monitoring images built; Compose preflight/config and 17 Prometheus alert rules passed; every current scrape target was up; health/readiness, trusted-host rejection, public metrics denial, internal metrics, and production OpenAPI 404 passed.
- TLS/logging/cleanup: TLS template passed `nginx -t` with a disposable certificate; synthetic secrets were absent from service logs; the `myvita-p6-sim` containers, networks and volumes and disposable databases were removed.

## 20. Final gate

- **P6 TECHNICAL INFRASTRUCTURE READINESS: YES** — repository-side architecture, controls, templates, preflight and simulation are complete.
- **P6 PRODUCTION DEPLOYMENT READINESS: NO** — required external infrastructure and evidence do not exist.
- **CLINICAL PILOT READINESS: NO** — infrastructure, operations and privacy/legal blockers remain.
