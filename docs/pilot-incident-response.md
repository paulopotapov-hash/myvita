# Pilot incident response

For loss of account access, first determine whether the account is inactive, an invitation is merely expired, or credentials are lost. A clinic admin may reactivate a deliberately disabled staff account; this does not reset its password and increments `token_epoch`. Replace an unaccepted invitation through the invitation flow. For an accepted account with a lost password, follow controlled support escalation until the recovery identity/delivery design in `p6-mfa-password-recovery.md` is approved — **DECISÃO NECESSÁRIA**. Never send a plaintext password or expose an existing hash/session token.

Named incident lead, privacy contact, infrastructure owner, clinic owner and escalation channels must be supplied before a real pilot. Preserve timestamps, request IDs, audit/log evidence and backups; do not copy clinical payloads into chat or tickets.

## Compromised account

1. Clinic admin deactivates the account, which increments the token epoch and revokes sessions.
2. Preserve audit/application/proxy logs and identify time, role, tenant and affected actions.
3. Contain affected access and rotate any exposed infrastructure credential separately.
4. Verify activity and tenant scope; do not reactivate informally.
5. Recovery/password action requires approved identity verification. MFA and self-service recovery do not exist.

## Compromised invitation

Before acceptance, issue a replacement invitation for the same clinic/email; this revokes pending predecessors. Do not forward the exposed token. After suspected acceptance, treat it as account compromise, deactivate the user and inspect audit events.

## Suspected cross-tenant access

Block the suspected account, preserve logs/database/backups, record identifiers without clinical content, determine affected resources/tenants and stop traffic if containment is uncertain. Escalate to the named privacy/legal owners for notification decisions. Do not delete evidence.

## Database incident

Remove application traffic/writes, preserve host/storage/log evidence, assess database and backup integrity, and recover only from a checksum-verified backup into an isolated target first. Restore live service only with incident-lead approval and post-restore validation.

## Closure

Record timeline, impact, root cause, actions, recovery evidence and follow-ups. Notification thresholds/timelines and regulatory reporting require jurisdiction-specific legal/privacy approval and are deliberately not asserted here.
