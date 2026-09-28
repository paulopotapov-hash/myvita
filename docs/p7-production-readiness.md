# P7-A production environment readiness

- Date: 2026-09-28
- Baseline: P6 `e362b2a`
- Branch: `p7a-production-environment`
- Scope: provisioning package only; no public deployment, real credentials or clinical data

## Executive summary

P7-A converts the P6 production topology into an operator-facing provisioning package: evidence-based host/network requirements, manual immutable image publication, digest-pinned deployment overlay, secret inventory, real-provider backup/restore contract, deployment/rollback runbook and HTTPS smoke script. It does not pretend that external resources exist.

MFA and self-service password recovery remain intentionally unimplemented. Current secure controls include Argon2id passwords, session revocation, invitations, rate limits and audit. Missing are WebAuthn/TOTP enrollment/challenge/recovery, verified delivery, reset-token model/service/UI, identity-verification policy and provider monitoring. These are production clinical blockers, not safe P7-A infrastructure shortcuts.

| Area | Status | Evidence | Blocker |
|---|---|---|---|
| Host | BLOCKED | host requirements documented | real qualified host absent |
| Firewall | BLOCKED | port/network matrix | real rules/evidence absent |
| Registry | PARTIAL | manual GHCR workflow + digest overlay | package policy/publication not proven |
| DNS | BLOCKED | DNS plan/runbook | real domain required |
| TLS | BLOCKED | TLS template/runbook | real trusted certificate required |
| Secrets | BLOCKED | inventory/injection/rotation plan | manager, values, custodians absent |
| PostgreSQL | PARTIAL | PG16 topology, pool, migrations, private network | real encrypted instance/roles absent |
| Backup | BLOCKED | verified local/S3-compatible tooling | real off-site storage required |
| Restore | BLOCKED | isolated restore procedure | real provider drill required |
| Monitoring | PARTIAL | Prometheus/Grafana/Alertmanager/exporters configuration | deployed retention/access evidence absent |
| Alerting | BLOCKED | rules and routing requirements | human destination required |
| MFA | BLOCKED | secure architecture decision | implementation/provider/policy absent |
| Password recovery | BLOCKED | token/delivery architecture | implementation/provider absent |
| Deployment | PARTIAL | reproducible runbook, overlays and preflight | target environment absent |
| Rollback | PARTIAL | image/config/migration/restore decision tree | release exercise absent |
| Smoke tests | PARTIAL | HTTPS/auth smoke script | real HTTPS environment/synthetic account absent |
| Security | PASS locally | P6 controls plus P7 validation | target-environment review still required |
| Documentation | PASS | seven requested P7 documents | external evidence must be appended |

## Validation results

- Backend: 119 tests passed with 95% coverage; Ruff passed; MyPy passed across 67 files.
- Frontend: 35 tests across 11 files, Oxlint, TypeScript/Vite production build and `npm audit` passed.
- Security: Bandit found zero medium/high issues; `pip-audit` found no known vulnerabilities; Gitleaks found no leaks in the working tree.
- Database/backup: Alembic upgrade→downgrade→upgrade and `alembic check` passed on disposable PostgreSQL; local and off-site backup script tests passed.
- Images/configuration: all five application images built; base+monitoring+registry Compose rendered with digest-shaped references; production preflight passed.
- Monitoring: Prometheus configuration and all 17 alert rules/tests passed.
- Packaging: smoke script syntax and HTTPS fail-closed behavior passed; `git diff --check` passed. Real HTTPS/authenticated smoke execution remains blocked by the absent environment and approved synthetic account.

## Final gates

- **P7-A TECHNICAL READINESS: YES** — repository-side provisioning package is complete after local validation.
- **P7-A PRODUCTION INFRASTRUCTURE READINESS: NO** — host, DNS/TLS, registry evidence, secrets, off-site recovery and alert delivery do not exist.
- **P7-A CLINICAL PILOT READINESS: NO** — infrastructure plus MFA/recovery, owners and privacy/legal gates remain open.

## Recommended next step

Name accountable owners and select/provision the host, approved domain, secret manager and private registry. Only then issue TLS and credentials, deploy digest-pinned images, prove real off-site restore and human alert delivery, and run the smoke suite before any clinical pilot decision.
