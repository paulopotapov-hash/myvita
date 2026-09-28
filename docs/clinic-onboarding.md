# Controlled clinic and user onboarding

Public clinic and patient registration are disabled by default. A production clinic must be created through a supervised bootstrap window or an approved administrative process, after identity and contractual checks outside the application. Disable the bootstrap flag immediately after the first clinic administrator exists.

## Invitation contract

- Only a clinic administrator can invite staff.
- A clinic administrator or verified clinical staff member can invite a patient.
- The server chooses the invitation clinic and role from the authenticated actor; neither can be supplied or changed during acceptance.
- Creating a replacement invitation revokes pending invitations for the same clinic and email.
- The opaque token is returned only once. Only its SHA-256 digest is stored.
- Tokens expire after `INVITATION_EXPIRE_HOURS` (24 by default, allowed range 1–168), are single-use, and are consumed under a database row lock.
- Acceptance creates the account and staff/patient profile in one database transaction and opens a session. Existing emails, expired/revoked/used tokens, extra payload fields, and role escalation are rejected.
- Creation and acceptance are recorded in the audit log without recording the token or password.

The frontend acceptance route is `/convite#token=<opaque-token>`. The URL fragment is not sent in HTTP requests; the frontend submits it in a POST body for preview/acceptance so proxies and browser request logs do not receive it as a query parameter. The API deliberately returns the token to the authorized inviter because no verified delivery provider has been selected. Until one is configured, an operator must transmit the one-time link through an approved authenticated channel and must not paste it into tickets, analytics, application logs, or shared chat. HTTPS is mandatory because possession of the token grants account creation.

Direct staff creation with an administrator-selected initial password is disabled by default and production refuses to enable it. `POST /api/v1/staff` remains available only behind `ALLOW_DIRECT_STAFF_CREATION=true` for legacy synthetic tests/development; deployments must use invitations.

## Account security

Authenticated users can change their password at `/app/seguranca`. The current password is required; the new password must satisfy the common strength policy. A successful change increments `token_epoch`, invalidating all older sessions, and issues a fresh cookie for the current browser.

Self-service password recovery and MFA are intentionally not simulated. They require a verified email/identity provider, recovery policy, rate limits, audit rules, support procedure, and product decision. Until implemented, recovery is a controlled support process with documented identity verification; operators must never set or transmit a plaintext password.

## Operator checklist

1. Verify the clinic administrator through the approved external process.
2. Confirm public registration flags are false.
3. Create the minimum required invitation and deliver it through the approved private channel.
4. Confirm acceptance and the expected role/clinic in the audit trail; never inspect or copy a password.
5. Revoke/replace an exposed pending invitation. Escalate suspected accepted-token compromise as an incident and invalidate sessions.

Clinic administrators can deactivate a staff or patient account through the tenant-scoped deactivation endpoints. Deactivation preserves clinical/audit history, increments `token_epoch`, and immediately rejects previously issued sessions. Cross-clinic targets are returned as not found, and an administrator cannot deactivate their own administrative account through the staff endpoint.
