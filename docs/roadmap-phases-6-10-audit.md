# Roadmap phases 6–10 — implementation and release audit

This record describes repository-local evidence only. It is not evidence that external infrastructure, clinical governance or legal/privacy decisions are complete.

## Phase 6 — account recovery and access lifecycle

Password change rotates `token_epoch` and issues a replacement session. Logout, staff deactivation/reactivation and role changes also rotate `token_epoch`, immediately invalidating older sessions. Inactive users receive the generic login failure. Invitations are random, stored as hashes, single-use and expire. Staff listing, role changes, deactivation and reactivation are clinic-admin-only where mutating, tenant-scoped and audited.

Password reset/recovery remains **BLOCKED — CONFIGURAÇÃO EXTERNA NECESSÁRIA**. A verified delivery and identity-recovery channel, sender/domain, provider credentials, abuse/rate policy, privileged-account recovery policy and named support owner must be approved before implementing issuance of reset links. No SMTP credentials or insecure support bypass were invented.

## Phase 7 — robust notifications

Appointment notifications are inserted in the same SQLAlchemy transaction as appointment creation, update and cancellation. Confirmed, completed and no-show transitions receive specific generic titles; notifications contain no clinical reason/content. Listing and read mutations remain scoped by both user and clinic. The frontend provides loading, empty, error, unread/read, per-item pending state and query invalidation after marking read.

Invitation delivery is not represented as an in-app notification because the invitee does not yet have an account. Its external delivery channel is part of the recovery/delivery blocker above.

## Phase 8 — real E2E

Playwright runs against a dedicated Compose project, database volume and non-default ports. The browser path proves Vite/proxy/API/PostgreSQL behavior with synthetic identities: clinic/admin onboarding, authorized area, staff creation, staff login, patient search, appointment creation/confirmation, clinical-record create/update, patient visibility, logout, expired-session redirect, role denial, cross-tenant denial and CSRF rejection. It never targets the normal local database.

## Phase 9 — security and reliability

Negative integration/E2E coverage exercises RBAC, tenant isolation/IDOR, 401/403/404 behavior, CSRF and session revocation. Existing controls retained include HttpOnly/SameSite cookies, environment-controlled Secure cookies, explicit TrustedHost/CORS lists, bounded rate limits, Pydantic validation, ORM queries, redacted structured logging and audit events. Role changes and access state changes revoke existing sessions.

Production secrets, TLS termination, forwarded-header trust boundaries, backup destination and restore ownership must still be validated in the actual deployment environment.

## Phase 10 — pilot readiness

The release gate is: full backend and frontend suites, Ruff, MyPy, TypeScript, ESLint, migration upgrade/downgrade/upgrade, Compose validation and isolated Playwright E2E. Repository runbooks cover backup/restore, incident response, access matrix, private environment and the clinical pilot contract.

The following remain **BLOCKED — CONFIGURAÇÃO EXTERNA NECESSÁRIA** before real clinical data: production domain/DNS and certificate, secret manager, encrypted immutable off-site backups plus restore drill, staffed alert receiver and escalation exercise, approved email/recovery delivery, named privacy/security/clinical owners, processor agreements and controller-approved retention/RPO/RTO.
